"""Concurrency on a real SQLite file with the production settings (WAL, busy timeout, FKs on).

SQLite allows one writer at a time. These tests check what that means for us: concurrent writers wait
instead of failing, and the atomic-claim patterns (approvals, workflows) still give exactly one winner.
"""
import threading

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.approvals import service
from app.approvals.service import ApprovalError
from app.core.security import Principal, Role
from app.db import models  # noqa: F401
from app.db.models import AuditEvent, Company, KpiRecord, OutboundMessage, WorkflowRun
from app.db.session import Base
from app.db.sqlite import configure_sqlite
from app.workflows import engine as wf_engine
from app.workflows.engine import Step, WorkflowDef

THREADS = 8


@pytest.fixture()
def factory(tmp_path):
    eng = configure_sqlite(create_engine(f"sqlite:///{tmp_path / 'c.db'}", connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    with sessionmaker(eng)() as db:
        db.add_all(Company(code=f"IC{i}", name=f"Co {i}") for i in range(1, 4))
        db.commit()
    yield sessionmaker(eng, expire_on_commit=False)
    eng.dispose()


def race(fn, n=THREADS):
    """Run fn(i) in n threads released together; return (results, errors)."""
    gate, results, errors = threading.Barrier(n), [], []

    def work(i):
        gate.wait()
        try:
            results.append(fn(i))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join(timeout=60) for t in ts]
    return results, errors


def test_concurrent_writers_wait_instead_of_failing_with_database_is_locked(factory):
    def write(i):
        with factory() as db:
            cid = db.scalar(select(Company.id).where(Company.code == "IC1"))
            for k in range(40):
                db.add(KpiRecord(company_id=cid, kpi_key=f"k{i}_{k}", period="2026-10", achievement=1.0, source="t"))
                db.add(AuditEvent(actor=f"t{i}", role="admin", action="x"))
                db.commit()  # many small writes, like real request traffic

    _, errors = race(write)
    assert errors == []
    with factory() as db:
        assert db.query(KpiRecord).count() == THREADS * 40 and db.query(AuditEvent).count() == THREADS * 40


def test_exactly_one_of_many_simultaneous_approvals_runs_the_action(factory):
    alice, admins = Principal("alice", Role.ADMIN, None), [Principal(f"admin{i}", Role.ADMIN, None) for i in range(THREADS)]
    with factory() as db:
        aid = service.submit(db, alice, "send_kpi_reminder", {"company_codes": ["IC1"], "period": "2026-10"}).approval.id

    def approve(i):
        with factory() as db:
            return service.decide(db, admins[i], aid, "approve", None).status

    won, errors = race(approve)
    assert len(won) == 1 and won == ["executed"]
    assert len(errors) == THREADS - 1 and all(isinstance(e, ApprovalError) and e.status == 409 for e in errors)
    with factory() as db:
        assert db.query(OutboundMessage).count() == 1     # sent once, not once per click


def test_only_one_worker_can_claim_and_run_a_workflow(factory):
    calls, lock = [], threading.Lock()

    def step(name):
        def run(ctx):
            with lock:
                calls.append(name)
            return {}
        return run

    wf = WorkflowDef("demo", "Demo", tuple(Step(n, n, step(n)) for n in ("a", "b", "c")), lambda ctx: {})
    with factory() as db:
        rid = wf_engine.create_run(db, Principal("u", Role.VIEWER, None), wf, "2026-10").id
    statuses, errors = race(lambda i: wf_engine.execute(factory, wf, rid))
    assert errors == [] and sorted(calls) == ["a", "b", "c"]          # each step ran exactly once overall
    with factory() as db:
        assert db.get(WorkflowRun, rid).status == "succeeded"
    assert "succeeded" in statuses


def test_foreign_keys_are_enforced(factory):
    from sqlalchemy.exc import IntegrityError
    with factory() as db:
        db.add(KpiRecord(company_id=9999, kpi_key="k", period="2026-10", achievement=1.0, source="t"))
        with pytest.raises(IntegrityError):
            db.commit()
