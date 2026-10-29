import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.security import Role, make_token
from app.db import models  # noqa: F401
from app.db.models import Alert, AuditEvent, Company, JobSchedule, KpiRecord, WorkflowRun
from app.db.session import Base, get_db
from app.db.sqlite import configure_sqlite
from app.knowledge.store import ensure_fts
from app.main import app
from app.scheduler import cadence as cad
from app.scheduler import jobs, runner
from tests.api.conftest import client  # noqa: F401


def dt(*a):
    return datetime(*a, tzinfo=UTC)


# --- cadence ---

@pytest.mark.parametrize("cadence,after,expected", [
    ({"type": "daily", "time": "06:00"}, dt(2026, 10, 29, 5, 0), dt(2026, 10, 29, 6, 0)),
    ({"type": "daily", "time": "06:00"}, dt(2026, 10, 29, 6, 0), dt(2026, 10, 30, 6, 0)),      # exactly now means the next one
    ({"type": "daily", "time": "06:00"}, dt(2026, 12, 31, 7, 0), dt(2027, 1, 1, 6, 0)),        # year rollover
    ({"type": "weekly", "weekday": 0, "time": "08:30"}, dt(2026, 10, 29, 9, 0), dt(2026, 11, 2, 8, 30)),   # Thursday -> Monday
    ({"type": "weekly", "weekday": 3, "time": "08:30"}, dt(2026, 10, 29, 9, 0), dt(2026, 11, 5, 8, 30)),   # Thursday after 08:30
    ({"type": "weekly", "weekday": 3, "time": "08:30"}, dt(2026, 10, 29, 8, 0), dt(2026, 10, 29, 8, 30)),
    ({"type": "monthly", "day": 2, "time": "06:00"}, dt(2026, 10, 1, 0, 0), dt(2026, 10, 2, 6, 0)),
    ({"type": "monthly", "day": 2, "time": "06:00"}, dt(2026, 10, 29, 0, 0), dt(2026, 11, 2, 6, 0)),
    ({"type": "monthly", "day": 2, "time": "06:00"}, dt(2026, 12, 29, 0, 0), dt(2027, 1, 2, 6, 0)),
    ({"type": "monthly", "day": 28, "time": "23:59"}, dt(2027, 1, 30, 0, 0), dt(2027, 2, 28, 23, 59)),   # February is fine
])
def test_next_run_times(cadence, after, expected):
    assert cad.next_after(cad.validate(cadence), after) == expected


@pytest.mark.parametrize("bad", [{}, {"type": "hourly", "time": "06:00"}, {"type": "daily"}, {"type": "daily", "time": "6am"},
                                 {"type": "daily", "time": "24:00"}, {"type": "weekly", "time": "06:00"},
                                 {"type": "weekly", "weekday": 7, "time": "06:00"}, {"type": "monthly", "time": "06:00"},
                                 {"type": "monthly", "day": 31, "time": "06:00"}, {"type": "monthly", "day": 0, "time": "06:00"}])
def test_invalid_cadences_are_refused(bad):
    with pytest.raises(cad.CadenceError):
        cad.validate(bad)


def test_periods_for_jobs():
    assert jobs.resolve_period("current", dt(2026, 10, 29)) == "2026-10"
    assert jobs.resolve_period("previous", dt(2026, 10, 29)) == "2026-09"
    assert jobs.resolve_period("previous", dt(2026, 1, 2)) == "2025-12"
    assert jobs.resolve_period("2026-04", dt(2026, 10, 29)) == "2026-04"
    with pytest.raises(jobs.JobFailed):
        jobs.resolve_period("soon", dt(2026, 10, 29))


# --- claim and run ---

@pytest.fixture()
def factory(tmp_path):
    eng = configure_sqlite(create_engine(f"sqlite:///{tmp_path / 's.db'}", connect_args={"check_same_thread": False}))
    Base.metadata.create_all(eng)
    ensure_fts(eng)
    f = sessionmaker(eng, expire_on_commit=False)
    with f() as db:
        db.add_all(Company(code=f"IC{i}", name=f"Co {i}") for i in range(1, 4))
        db.commit()
    yield f
    eng.dispose()


def schedule(factory, job="ingest", due=dt(2026, 10, 29, 6, 0), enabled=True, cadence=None, params=None):
    with factory() as db:
        s = JobSchedule(job=job, name=f"{job} job", cadence=cadence or {"type": "daily", "time": "06:00"}, params=params,
                        enabled=enabled, next_run_at=due, created_by="t")
        db.add(s)
        db.commit()
        return s.id


NOW = dt(2026, 10, 29, 6, 5)


def test_only_due_enabled_unclaimed_jobs_are_claimed(factory):
    due = schedule(factory)
    schedule(factory, due=dt(2026, 10, 29, 7, 0))                    # not yet due
    schedule(factory, enabled=False)                                  # switched off
    assert runner.claim_due(factory, NOW) == [due]
    assert runner.claim_due(factory, NOW) == []                       # already claimed: not claimed twice


def test_a_job_runs_once_even_when_many_ticks_race(factory):
    sid = schedule(factory)
    ran, lock = [], threading.Lock()

    def counting(db, params, now, deps):
        with lock:
            ran.append(1)
        return "ok"

    jobs.JOBS["ingest"], original = counting, jobs.JOBS["ingest"]
    try:
        gate, results = threading.Barrier(6), []

        def work():
            gate.wait()
            results.append(runner.tick(factory, NOW, {}))
        ts = [threading.Thread(target=work) for _ in range(6)]
        [t.start() for t in ts]
        [t.join(timeout=30) for t in ts]
    finally:
        jobs.JOBS["ingest"] = original
    assert len(ran) == 1 and sum(len(r) for r in results) == 1
    with factory() as db:
        s = db.get(JobSchedule, sid)
        assert s.last_status == "success" and s.claimed_at is None
        assert s.next_run_at == dt(2026, 10, 30, 6, 0)                  # rescheduled for tomorrow


def test_ingest_job_loads_data_and_reports_what_it_did(factory):
    sid = schedule(factory, params={"period": "current"})
    assert runner.tick(factory, NOW, {}) == {sid: "success"}
    with factory() as db:
        s = db.get(JobSchedule, sid)
        assert s.last_detail.startswith("2026-10: 4 sources") and db.query(KpiRecord).filter_by(period="2026-10").count() == 3 * 19
        assert db.scalar(select(AuditEvent.action).where(AuditEvent.action == "scheduled_job")) == "scheduled_job"


def test_monthly_review_job_creates_the_previous_months_report_without_publishing_it(factory):
    ing = schedule(factory, due=dt(2026, 10, 29, 6, 0), params={"period": "2026-09"})
    rev = schedule(factory, job="monthly_review", due=dt(2026, 10, 29, 6, 0))
    out = runner.tick(factory, NOW, {"factory": factory, "llm": None})
    assert out == {ing: "success", rev: "success"}
    with factory() as db:
        run = db.scalar(select(WorkflowRun))
        assert run.period == "2026-09" and run.status == "succeeded" and run.requested_by == "scheduler"
        assert "publishing still needs approval" in db.get(JobSchedule, rev).last_detail


def test_a_failing_job_is_recorded_alerts_and_still_rescheduled(factory):
    def boom(db, params, now, deps):
        raise RuntimeError("password=hunter2")

    sid = schedule(factory, job="monthly_review")
    jobs.JOBS["monthly_review"], original = boom, jobs.JOBS["monthly_review"]
    try:
        assert runner.tick(factory, NOW, {}) == {sid: "failed"}
    finally:
        jobs.JOBS["monthly_review"] = original
    with factory() as db:
        s = db.get(JobSchedule, sid)
        assert s.last_status == "failed" and "RuntimeError" in s.last_detail and "hunter2" not in s.last_detail
        assert s.claimed_at is None and s.next_run_at == dt(2026, 10, 30, 6, 0)           # it will try again tomorrow
        a = db.scalar(select(Alert))
        assert a.kind == "scheduled_job_failed" and a.company_id is None and "failed" in a.title


def test_a_job_orphaned_by_a_crash_is_released_but_a_live_one_is_not(factory):
    old, fresh = schedule(factory), schedule(factory)
    with factory() as db:
        db.get(JobSchedule, old).claimed_at = NOW - timedelta(hours=3)
        db.get(JobSchedule, fresh).claimed_at = NOW - timedelta(minutes=1)
        db.commit()
    assert runner.release_orphans(factory, NOW) == 1
    with factory() as db:
        assert db.get(JobSchedule, old).claimed_at is None and db.get(JobSchedule, fresh).claimed_at is not None


# --- API ---

def h(user, role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE = h("alice")


def test_schedule_api_validates_and_is_admin_only(client):
    body = {"job": "ingest", "name": "Nightly load", "cadence": {"type": "daily", "time": "02:00"}}
    r = client.post("/schedules", json=body, headers=ALICE)
    assert r.status_code == 201 and r.json()["enabled"] and r.json()["next_run_at"] and r.json()["params"] == {}
    for bad in ({**body, "job": "format_disk"}, {**body, "cadence": {"type": "daily", "time": "25:00"}},
                {**body, "params": {"color": "red"}}, {**body, "params": {"period": "soonish"}},
                {**body, "params": {"sources": ["nope"]}}, {**body, "job": "monthly_review", "params": {"sources": ["registry"]}}):
        assert client.post("/schedules", json=bad, headers=ALICE).status_code == 422
    for who in (h("e", Role.EDITOR), h("v", Role.VIEWER), h("s", Role.ADMIN, [1])):
        assert client.get("/schedules", headers=who).status_code == 403
        assert client.post("/schedules", json=body, headers=who).status_code == 403


def test_schedule_update_disable_delete_and_run_now(client):
    sid = client.post("/schedules", json={"job": "ingest", "name": "Load", "cadence": {"type": "daily", "time": "02:00"},
                                          "params": {"period": "2026-10"}}, headers=ALICE).json()["id"]
    r = client.patch(f"/schedules/{sid}", json={"cadence": {"type": "monthly", "day": 3, "time": "07:15"}, "enabled": False}, headers=ALICE)
    assert r.json()["cadence"] == {"type": "monthly", "day": 3, "time": "07:15"} and r.json()["enabled"] is False
    assert client.patch(f"/schedules/{sid}", json={"cadence": {"type": "daily", "time": "99:00"}}, headers=ALICE).status_code == 422
    assert client.patch("/schedules/99", json={"enabled": True}, headers=ALICE).status_code == 404
    run = client.post(f"/schedules/{sid}/run-now", headers=ALICE).json()                  # works even while disabled
    assert run["status"] == "success" and run["schedule"]["last_detail"].startswith("2026-10") and not run["schedule"]["running"]
    db = next(app.dependency_overrides[get_db]())
    assert db.query(KpiRecord).filter_by(period="2026-10").count() == 3 * 19
    db.execute(JobSchedule.__table__.update().values(claimed_at=datetime.now(UTC)))
    db.commit()
    assert client.post(f"/schedules/{sid}/run-now", headers=ALICE).status_code == 409    # already running
    assert client.post("/schedules/99/run-now", headers=ALICE).status_code == 404
    assert client.delete(f"/schedules/{sid}", headers=ALICE).status_code == 204
    assert client.get("/schedules", headers=ALICE).json() == []
