from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import Principal, Role, make_token
from app.db.models import (
    Alert,
    ApprovalEvent,
    ApprovalRequest,
    AuditEvent,
    Company,
    IngestionRun,
    JobSchedule,
    WorkflowEvent,
    WorkflowRun,
)
from app.db.session import get_db
from app.services import timeline

from .conftest import auth, client  # noqa: F401

BASE = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def h(user: str, role: Role = Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


@pytest.fixture()
def db(client):
    d = next(client.app.dependency_overrides[get_db]())
    yield d
    d.close()


def seed(db, at: datetime = BASE) -> None:
    """One row from every source, each a minute apart so the ordering is unambiguous."""
    db.add(AuditEvent(at=at, actor="alice", role="admin", action="copilot_tool", target="get_group_score"))
    db.add(AuditEvent(at=at - timedelta(minutes=1), actor="bob", role="viewer",
                      action="copilot_tool", target="rank_ics"))
    run = WorkflowRun(workflow="monthly_review", period="2026-10", status="succeeded",
                      requested_by="alice", role="admin", state={})
    db.add(run)
    db.flush()
    db.add(WorkflowEvent(run_id=run.id, seq=1, at=at - timedelta(minutes=2), step="collect",
                         status="done", message="Collect scorecards"))
    db.add(IngestionRun(source="successfactors", mode="stub", period="2026-10", status="success",
                        companies_ok=3, records_written=42, started_at=at - timedelta(minutes=3)))
    req = ApprovalRequest(action="create_snapshot", risk="internal_write", summary="Save snapshot",
                          args={}, requested_by="alice", via="api", status="pending")
    db.add(req)
    db.flush()
    db.add(ApprovalEvent(approval_id=req.id, at=at - timedelta(minutes=4), actor="alice", event="submitted"))
    db.add(JobSchedule(job="ingest", name="Nightly ingest", cadence={"type": "daily", "time": "02:00"},
                       next_run_at=at, last_run_at=at - timedelta(minutes=5), last_status="success",
                       last_detail="2026-10: 4 sources", created_by="alice"))
    db.add(Alert(kind="watch_fired", severity="medium", company_id=1, entity="IC1", period="2026-10",
                 title="Watch 'Retention': 72.0 below 80", dedupe_key="watch:1:2026-10",
                 audience_user_id="alice", created_at=at - timedelta(minutes=6)))
    db.commit()


def test_the_feed_merges_six_sources_in_descending_time(client, db):
    seed(db)
    body = client.get("/timeline", headers=h("alice")).json()
    assert [i["source"] for i in body["items"]] == [
        "audit", "audit", "workflow", "ingestion", "approval", "schedule", "watch"]
    assert [i["at"] for i in body["items"]] == sorted((i["at"] for i in body["items"]), reverse=True)
    assert body["items"][0]["title"] == "Used tool get_group_score"
    assert body["items"][0]["id"].startswith("audit:")


def test_the_cursor_pages_without_dropping_items_that_share_a_timestamp(client, db):
    """Two sources at the identical instant: a bare `at <` cursor would lose whichever sorted second."""
    db.add(AuditEvent(at=BASE, actor="alice", role="admin", action="copilot_tool", target="t"))
    db.add(IngestionRun(source="peoplestrong", mode="stub", period="2026-10", status="success",
                        started_at=BASE))
    run = WorkflowRun(workflow="monthly_review", period="2026-10", status="succeeded",
                      requested_by="alice", role="admin", state={})
    db.add(run)
    db.flush()
    db.add(WorkflowEvent(run_id=run.id, seq=1, at=BASE, step="collect", status="done", message="m"))
    db.commit()

    seen, cursor, pages = [], None, 0
    while pages < 10:
        body = client.get(f"/timeline?limit=1&cursor={cursor or ''}", headers=h("alice")).json()
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        pages += 1
        if not cursor:
            break
    assert len(seen) == 3 and len(set(seen)) == 3  # every row exactly once, none lost to the tie


def test_a_non_admin_sees_only_their_own_tool_calls_and_approvals(client, db):
    seed(db)
    body = client.get("/timeline", headers=h("bob", Role.VIEWER)).json()
    actors = {i["actor"] for i in body["items"] if i["source"] == "audit"}
    assert actors == {"bob"}  # never alice's Copilot activity
    assert [i for i in body["items"] if i["source"] == "approval"] == []


def test_a_scoped_user_sees_no_workflow_ingestion_or_schedule_items(client, db):
    seed(db)
    body = client.get("/timeline", headers=h("alice", Role.ADMIN, [1])).json()
    assert {i["source"] for i in body["items"]} & {"workflow", "ingestion", "schedule"} == set()


def test_a_private_watch_alert_reaches_only_its_owner(client, db):
    seed(db)
    mine = client.get("/timeline?kinds=watch_fired", headers=h("alice")).json()
    theirs = client.get("/timeline?kinds=watch_fired", headers=h("carol")).json()
    assert len(mine["items"]) == 1
    assert theirs["items"] == []  # carol is a group-wide admin and still must not see alice's watch


def test_kinds_and_company_id_filters_narrow_the_feed(client, db):
    seed(db)
    only_tools = client.get("/timeline?kinds=tool", headers=h("alice")).json()
    assert {i["kind"] for i in only_tools["items"]} == {"tool"}

    by_company = client.get("/timeline?company_id=1", headers=h("alice")).json()
    assert {i["company_id"] for i in by_company["items"]} == {1}


def test_a_company_filter_outside_your_scope_is_refused(client, db):
    seed(db)
    assert client.get("/timeline?company_id=3", headers=h("alice", Role.VIEWER, [1])).status_code == 403


def test_audit_remains_admin_only(client, db):
    seed(db)
    assert client.get("/audit", headers=h("bob", Role.VIEWER)).status_code == 403
    assert client.get("/timeline", headers=h("bob", Role.VIEWER)).status_code == 200


def test_a_malformed_cursor_starts_from_the_top_rather_than_erroring(client, db):
    seed(db)
    body = client.get("/timeline?cursor=not-a-cursor", headers=h("alice")).json()
    assert len(body["items"]) == 7


def test_only_activity_actions_appear_not_the_whole_audit_log(client, db):
    db.add(AuditEvent(at=BASE, actor="alice", role="admin", action="schedule_created", target="ingest:x"))
    db.add(AuditEvent(at=BASE, actor="alice", role="admin", action="copilot_delegate", target="ta_analyst"))
    db.commit()
    body = client.get("/timeline", headers=h("alice")).json()
    assert [i["kind"] for i in body["items"]] == ["delegate"]
    assert body["items"][0]["title"] == "Delegated to ta_analyst"


def test_fetch_is_usable_without_http(client, db):
    """The service is the unit under test; the endpoint is a thin wrapper (as scorecard is)."""
    seed(db)
    out = timeline.fetch(db, Principal("alice", Role.ADMIN, None), limit=3)
    assert len(out["items"]) == 3 and out["next_cursor"]
    assert db.scalar(select(Company.code).where(Company.id == 1)) == "IC1"
