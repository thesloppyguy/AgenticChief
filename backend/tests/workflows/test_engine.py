from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import Principal, Role
from app.db import models  # noqa: F401
from app.db.models import WorkflowEvent, WorkflowRun
from app.db.session import Base
from app.db.sqlite import configure_sqlite
from app.workflows import engine
from app.workflows.engine import Step, WorkflowDef

WHO = Principal("u", Role.VIEWER, None)


@pytest.fixture()
def factory():
    eng = configure_sqlite(create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    return sessionmaker(eng, expire_on_commit=False)


def make_wf(calls, fail_at=None):
    def step(name):
        def run(ctx):
            calls.append(name)
            if name == fail_at:
                raise ConnectionError("password=hunter2 host=db.internal")
            return {"from": name, "saw": sorted(ctx.state)}
        return run
    return WorkflowDef("demo", "Demo", tuple(Step(n, n.title(), step(n)) for n in ("one", "two", "three")),
                       lambda ctx: {"order": list(ctx.state)})


def new_run(factory, wf):
    with factory() as db:
        return engine.create_run(db, WHO, wf, "2026-10").id


def events(factory, run_id):
    with factory() as db:
        return [(e.step, e.status) for e in db.scalars(select(WorkflowEvent).where(WorkflowEvent.run_id == run_id).order_by(WorkflowEvent.seq))]


def test_runs_steps_in_order_passing_earlier_outputs_forward(factory):
    calls = []
    wf = make_wf(calls)
    rid = new_run(factory, wf)
    assert engine.execute(factory, wf, rid) == "succeeded"
    assert calls == ["one", "two", "three"]
    with factory() as db:
        run = db.get(WorkflowRun, rid)
        assert run.result == {"order": ["one", "two", "three"]} and run.finished_at
        assert run.state["three"]["saw"] == ["one", "two"]
    assert events(factory, rid)[-1] == ("run", "done")


def test_failure_records_type_only_then_resume_skips_finished_steps(factory):
    calls = []
    rid = new_run(factory, make_wf(calls, fail_at="two"))
    seen = []
    assert engine.execute(factory, make_wf(calls, fail_at="two"), rid, on_failure=lambda db, r: seen.append(r.error)) == "failed"
    with factory() as db:
        run = db.get(WorkflowRun, rid)
        assert run.status == "failed" and run.error == "ConnectionError" and list(run.state) == ["one"]
    assert seen == ["ConnectionError"]
    assert "hunter2" not in str(events(factory, rid)) and "db.internal" not in str(events(factory, rid))
    calls.clear()
    assert engine.execute(factory, make_wf(calls), rid) == "succeeded"     # the cause is fixed: resume
    assert calls == ["two", "three"]                                          # step "one" was not redone
    assert ("one", "skipped") in events(factory, rid)


def test_only_one_worker_can_claim_a_run(factory):
    calls = []
    wf = make_wf(calls)
    rid = new_run(factory, wf)
    with factory() as db:                                  # another worker already holds it
        db.get(WorkflowRun, rid).status = "running"
        db.commit()
    assert engine.execute(factory, wf, rid) == "running" and calls == []
    with factory() as db:
        db.get(WorkflowRun, rid).status = "succeeded"
        db.commit()
    assert engine.execute(factory, wf, rid) == "succeeded" and calls == []   # never re-run a finished run
    assert engine.execute(factory, wf, 9999) == "missing"


def test_stale_running_run_is_interrupted_and_resumable_but_live_one_is_left_alone(factory):
    calls = []
    wf = make_wf(calls)
    dead, alive = new_run(factory, wf), new_run(factory, wf)
    now = datetime.now(UTC)
    with factory() as db:
        d, a = db.get(WorkflowRun, dead), db.get(WorkflowRun, alive)
        d.status, d.heartbeat_at, d.state = "running", now - timedelta(minutes=30), {"one": {"from": "one", "saw": []}}
        a.status, a.heartbeat_at = "running", now
        db.commit()
    with factory() as db:
        assert engine.sweep_stale(db, 300) == 1
        assert db.get(WorkflowRun, dead).status == "interrupted" and db.get(WorkflowRun, alive).status == "running"
    assert engine.execute(factory, wf, dead) == "succeeded"
    assert calls == ["two", "three"]                       # picked up after the step that finished before the crash
