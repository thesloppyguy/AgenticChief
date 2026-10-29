import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.alerts.engine import prev_period
from app.api.workflows import get_llm
from app.copilot.tools import run_tool
from app.core.security import Principal, Role, make_token
from app.db.models import Alert, ImmutableRecordError, ReportSnapshot, WorkflowRun
from app.db.session import get_db
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS
from app.ingestion.stub import StubExtractor
from app.main import app
from app.reports import monthly_review
from app.reports.integrity import canonical_hash
from app.workflows.engine import Step
from tests.api.conftest import client  # noqa: F401

P = "2026-10"


def h(user, role, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE, BOB, VIC = h("alice", Role.ADMIN), h("bob", Role.ADMIN), h("vic", Role.VIEWER)
SCOPED = h("sam", Role.EDITOR, [1])


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


@pytest.fixture()
def data(db):
    ex = {s: StubExtractor(s) for s in SOURCE_KPIS}
    for p in (prev_period(P), P):
        ingest(db, p, ex)


def start(client, headers=VIC, period=P):
    return client.post("/workflows/monthly-review/runs", json={"period": period}, headers=headers)


def test_run_completes_with_progress_result_and_lineage(client, data):
    r = start(client)
    assert r.status_code == 202
    run = client.get(f"/workflows/runs/{r.json()['id']}", headers=VIC).json()
    assert run["status"] == "succeeded" and all(s["done"] for s in run["steps"])
    assert [e["step"] for e in run["events"] if e["status"] == "done"][-5:] == ["collect", "lineage", "build", "commentary", "run"]
    rep = run["result"]
    assert rep["meta"]["period"] == P and rep["meta"]["previous_period"] == "2026-09"
    assert rep["meta"]["synthetic_data"] is True and any("synthetic" in c for c in rep["caveats"])
    assert rep["commentary"]["method"] == "template" and rep["commentary"]["issues"] == ["no_llm_configured"]
    assert rep["headline"]["delta"] is not None and rep["lineage"]["data_origin"]["stub"] > 0
    assert {s["source"] for s in rep["lineage"]["sources"]} == set(SOURCE_KPIS)
    assert client.get(f"/workflows/runs/{run['id']}", params={"after_seq": 3}, headers=VIC).json()["events"][0]["seq"] == 4
    md = client.get(f"/workflows/runs/{run['id']}/markdown", headers=VIC)
    assert md.status_code == 200 and md.text.startswith("# Group HR Scorecard") and "Synthetic data" in md.text


def test_report_scores_match_the_scoreboard_exactly(client, data):
    rep = client.get(f"/workflows/runs/{start(client).json()['id']}", headers=VIC).json()["result"]
    sc = client.get("/scorecard", params={"period": P}, headers=ALICE).json()
    assert rep["headline"]["group_score"] == round(sc["group"]["score"], 1)   # no number of its own
    assert rep["headline"]["distribution"]["red"] == sum(c["status"] == "red" for c in sc["companies"])


def test_only_group_wide_users_can_use_reports(client, data):
    assert start(client, SCOPED).status_code == 403
    rid = start(client).json()["id"]
    assert client.get(f"/workflows/runs/{rid}", headers=SCOPED).status_code == 403
    assert client.get("/workflows/runs", headers=SCOPED).status_code == 403
    assert client.get(f"/workflows/runs/{rid}/markdown", headers=SCOPED).status_code == 403
    assert start(client, period="2026-13").status_code == 422


def test_failed_run_alerts_then_resumes_without_redoing_finished_steps(client, data, db, monkeypatch):
    calls = []

    def counting(step):
        def run(ctx):
            calls.append(step.key)
            return step.run(ctx)
        return dataclasses.replace(step, run=run)

    def boom(ctx):
        raise ValueError("secret detail")

    wf = monthly_review.WORKFLOW
    broken = dataclasses.replace(wf, steps=tuple(
        Step(s.key, s.label, boom) if s.key == "build" else counting(s) for s in wf.steps))
    monkeypatch.setattr(monthly_review, "WORKFLOW", broken)
    rid = start(client).json()["id"]
    run = client.get(f"/workflows/runs/{rid}", headers=VIC).json()
    assert run["status"] == "failed" and run["error"] == "ValueError" and "secret" not in str(run)
    assert [a.kind for a in db.scalars(select(Alert))] == ["workflow_failed"]
    assert calls == ["collect", "lineage"]
    monkeypatch.setattr(monthly_review, "WORKFLOW", dataclasses.replace(wf, steps=tuple(counting(s) for s in wf.steps)))
    calls.clear()
    assert client.post(f"/workflows/runs/{rid}/resume", headers=VIC).status_code == 202
    assert client.get(f"/workflows/runs/{rid}", headers=VIC).json()["status"] == "succeeded"
    assert calls == ["build", "commentary"]                       # collect and lineage were not repeated
    assert client.post(f"/workflows/runs/{rid}/resume", headers=VIC).status_code == 409   # finished
    assert client.post("/workflows/runs/9999/resume", headers=VIC).status_code == 404


def test_run_left_running_by_a_dead_worker_is_detected_and_resumable(client, data, db):
    rid = start(client).json()["id"]
    db.execute(update(WorkflowRun).where(WorkflowRun.id == rid).values(
        status="running", result=None, heartbeat_at=datetime.now(UTC) - timedelta(hours=1)))
    db.commit()
    assert client.get(f"/workflows/runs/{rid}", headers=VIC).json()["status"] == "interrupted"
    client.post(f"/workflows/runs/{rid}/resume", headers=VIC)
    assert client.get(f"/workflows/runs/{rid}", headers=VIC).json()["status"] == "succeeded"


# --- publishing: approval, immutability, verification ---

def propose(client, rid, headers=ALICE):
    return client.post("/approvals", json={"action": "publish_monthly_report", "args": {"run_id": rid}}, headers=headers)


def approve(client, aid, headers=BOB):
    return client.post(f"/approvals/{aid}/decision", json={"decision": "approve"}, headers=headers)


def test_publish_needs_approval_and_produces_a_verifiable_immutable_snapshot(client, data, db):
    rid = start(client).json()["id"]
    p = propose(client, rid).json()
    assert p["verdict"] == "require_approval" and db.query(ReportSnapshot).count() == 0   # nothing published yet
    res = approve(client, p["approval"]["id"]).json()
    assert res["status"] == "executed"
    snap = client.get(f"/reports/snapshots/{res['result']['snapshot_id']}", headers=VIC).json()
    assert snap["kind"] == "monthly_review" and snap["run_id"] == rid and snap["created_by"] == "bob"
    assert snap["verified"] is True and snap["content_hash"] == res["result"]["content_hash"]
    assert snap["payload"]["commentary"]["text"]
    listing = client.get("/reports/snapshots", headers=VIC).json()
    assert listing[0]["kind"] == "monthly_review" and listing[0]["content_hash"] == snap["content_hash"]
    assert client.get(f"/reports/snapshots/{snap['id']}/markdown", headers=VIC).text.startswith("# Group HR")
    # a second publication of the same run is refused before anyone is asked
    assert propose(client, rid).status_code == 422


def test_publish_rejects_runs_that_cannot_be_published(client, data, db):
    assert propose(client, 999).status_code == 422                 # unknown
    rid = start(client).json()["id"]
    db.execute(update(WorkflowRun).where(WorkflowRun.id == rid).values(status="failed", result=None))
    db.commit()
    assert propose(client, rid).status_code == 422                 # not finished


def test_scoped_admin_cannot_even_propose_publishing(client, data):
    rid = start(client).json()["id"]
    r = propose(client, rid, headers=h("sa", Role.ADMIN, [1])).json()
    assert r["verdict"] == "deny" and "group-wide" in r["reason"]


def test_publish_cannot_be_approved_by_a_scoped_admin(client, data):
    rid = start(client).json()["id"]
    aid = propose(client, rid).json()["approval"]["id"]
    assert approve(client, aid, headers=h("sa", Role.ADMIN, [1])).status_code == 403


def test_ai_commentary_flows_through_the_workflow_only_when_grounded(client, data):
    from tests.reports.test_builder_commentary import FakeClient
    score = round(client.get("/scorecard", params={"period": P}, headers=ALICE).json()["group"]["score"], 1)
    app.dependency_overrides[get_llm] = lambda: FakeClient(f"The Group score is {score}.")
    ok = client.get(f"/workflows/runs/{start(client).json()['id']}", headers=VIC).json()["result"]["commentary"]
    assert ok["method"] == "ai" and str(score) in ok["text"]
    app.dependency_overrides[get_llm] = lambda: FakeClient("The Group score is 12.3.")
    bad = client.get(f"/workflows/runs/{start(client).json()['id']}", headers=VIC).json()["result"]["commentary"]
    assert bad["method"] == "template" and bad["issues"][0].startswith("rejected_ungrounded_numbers")


def test_a_published_snapshot_cannot_be_changed_and_tampering_is_detected(client, data, db):
    rid = start(client).json()["id"]
    sid = approve(client, propose(client, rid).json()["approval"]["id"]).json()["result"]["snapshot_id"]
    snap = db.get(ReportSnapshot, sid)
    snap.period = "2020-01"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()
    db.delete(db.get(ReportSnapshot, sid))
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()
    # someone edits the stored payload behind the application's back: verification catches it
    stored = db.get(ReportSnapshot, sid).payload
    db.execute(update(ReportSnapshot).where(ReportSnapshot.id == sid).values(
        payload={**stored, "headline": {**stored["headline"], "group_score": 99.9}}))
    db.commit()
    assert client.get(f"/reports/snapshots/{sid}", headers=VIC).json()["verified"] is False


def test_direct_admin_snapshot_is_hashed_too(client, data):
    sid = client.post("/reports/snapshots", params={"period": P}, headers=ALICE).json()["id"]
    got = client.get(f"/reports/snapshots/{sid}", headers=VIC).json()
    assert got["kind"] == "scorecard" and got["verified"] is True
    assert got["content_hash"] == canonical_hash(got["payload"])


def test_copilot_can_read_the_review_and_propose_publishing_but_nothing_more(client, data, db):
    who = Principal("alice", Role.ADMIN, None)
    assert "no completed" in run_tool(db, who, "latest_monthly_review", {"period": P})["error"]
    rid = start(client).json()["id"]
    got = run_tool(db, who, "latest_monthly_review", {"period": P})
    assert got["run_id"] == rid and got["published_snapshot_id"] is None and got["commentary"]["text"]
    out = run_tool(db, who, "propose_action", {"action": "publish_monthly_report", "args": {"run_id": rid}})
    assert out["status"] == "pending" and db.query(ReportSnapshot).count() == 0
    assert "group-wide" in run_tool(db, Principal("sam", Role.EDITOR, frozenset({1})), "latest_monthly_review", {})["error"]
