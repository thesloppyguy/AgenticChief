import dataclasses

import pytest
from sqlalchemy import select

from app.approvals import actions as actions_mod
from app.approvals.service import ApprovalError, execute_approved
from app.copilot.tools import run_tool
from app.core.config import settings
from app.core.security import Principal, Role, make_token
from app.db.models import ApprovalRequest, OutboundMessage, ReportSnapshot
from app.db.session import get_db
from app.main import app
from tests.api.conftest import client  # noqa: F401

P = "2026-10"


def h(user: str, role: Role, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE = h("alice", Role.ADMIN)      # requester / second admin
BOB = h("bob", Role.ADMIN)          # approver
EDITOR = h("erin", Role.EDITOR)
VIEWER = h("vic", Role.VIEWER, [1])


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def submit(client, headers=ALICE, codes=("IC1",), **extra):
    body = {"action": "send_kpi_reminder", "args": {"company_codes": list(codes), "period": P, **extra}}
    return client.post("/approvals", json=body, headers=headers)


def decide(client, aid, decision, headers=BOB, comment=None):
    return client.post(f"/approvals/{aid}/decision", json={"decision": decision, "comment": comment}, headers=headers)


def test_pending_request_executes_nothing_until_approved(client, db):
    r = submit(client).json()
    assert r["verdict"] == "require_approval" and r["approval"]["status"] == "pending"
    assert db.query(OutboundMessage).count() == 0           # proposing sends nothing
    d = decide(client, r["approval"]["id"], "approve")
    assert d.status_code == 200 and d.json()["status"] == "executed"
    assert d.json()["result"]["queued"] == 1
    msgs = db.scalars(select(OutboundMessage)).all()
    assert [(m.company_code, m.status, m.approval_id) for m in msgs] == [("IC1", "queued", r["approval"]["id"])]
    hist = client.get(f"/approvals/{r['approval']['id']}", headers=BOB).json()["events"]
    assert [(e["actor"], e["event"]) for e in hist] == [
        ("alice", "submitted"), ("bob", "approved"), ("bob", "executed")]


def test_four_eyes_self_approval_blocked_unless_configured(client, monkeypatch):
    aid = submit(client).json()["approval"]["id"]
    assert decide(client, aid, "approve", headers=ALICE).status_code == 403
    monkeypatch.setattr(settings, "approval_allow_self_approval", True)
    assert decide(client, aid, "approve", headers=ALICE).json()["status"] == "executed"


def test_only_admins_decide(client):
    aid = submit(client).json()["approval"]["id"]
    for who in (EDITOR, VIEWER):
        assert decide(client, aid, "approve", headers=who).status_code == 403


def test_reject_and_request_changes_need_a_comment(client, db):
    aid = submit(client).json()["approval"]["id"]
    assert decide(client, aid, "reject").status_code == 422
    assert decide(client, aid, "request_changes", comment="  ").status_code == 422
    assert decide(client, aid, "reject", comment="not now").json()["status"] == "rejected"
    assert db.query(OutboundMessage).count() == 0


def test_changes_requested_then_resubmit_then_approve(client, db):
    aid = submit(client, note="old").json()["approval"]["id"]
    decide(client, aid, "request_changes", comment="narrow it to IC2")
    assert client.post(f"/approvals/{aid}/resubmit", json={"args": {"company_codes": ["IC2"], "period": P}},
                       headers=BOB).status_code == 403            # only the requester
    r = client.post(f"/approvals/{aid}/resubmit", json={"args": {"company_codes": ["IC2"], "period": P}}, headers=ALICE)
    assert r.json()["status"] == "pending" and r.json()["args"]["company_codes"] == ["IC2"]
    decide(client, aid, "approve")
    assert [m.company_code for m in db.scalars(select(OutboundMessage))] == ["IC2"]


def test_a_decision_can_only_be_made_once(client, db):
    aid = submit(client).json()["approval"]["id"]
    assert decide(client, aid, "approve").status_code == 200
    assert decide(client, aid, "approve").status_code == 409
    assert decide(client, aid, "reject", comment="late").status_code == 409
    assert db.query(OutboundMessage).count() == 1               # not executed twice


def test_policy_denial_is_recorded_and_cannot_be_approved(client, db):
    bulk = submit(client, codes=[f"IC{i}" for i in range(1, 8)])
    assert bulk.status_code == 201 and bulk.json()["verdict"] == "deny"
    aid = bulk.json()["approval"]["id"]
    assert bulk.json()["approval"]["status"] == "denied" and "bulk" in bulk.json()["reason"]
    assert decide(client, aid, "approve").status_code == 409     # denied, not pending
    assert db.query(OutboundMessage).count() == 0
    assert [e["event"] for e in client.get(f"/approvals/{aid}", headers=BOB).json()["events"]] == ["submitted", "denied"]


def test_scoped_requester_cannot_target_other_companies_and_learns_nothing(client):
    scoped = h("sam", Role.EDITOR, [1])
    other = submit(client, headers=scoped, codes=("IC2",)).json()
    ghost = submit(client, headers=scoped, codes=("IC999",)).json()
    assert other["verdict"] == ghost["verdict"] == "deny" and other["reason"] == ghost["reason"]
    assert submit(client, headers=scoped, codes=("IC1",)).json()["verdict"] == "require_approval"


def test_validation_and_unknown_action(client):
    assert submit(client, kpi_key="not_a_kpi").status_code == 422
    assert submit(client, codes=()).status_code == 422
    assert client.post("/approvals", json={"action": "format_disk", "args": {}}, headers=ALICE).status_code == 404
    assert client.post("/approvals", json={"action": "send_kpi_reminder", "args": {"period": "bad"}},
                       headers=ALICE).status_code == 422


def test_visibility_requester_sees_own_admin_sees_all(client):
    aid = submit(client, headers=h("carol", Role.EDITOR)).json()["approval"]["id"]
    assert client.get(f"/approvals/{aid}", headers=h("dave", Role.EDITOR)).status_code == 404
    assert client.get(f"/approvals/{aid}", headers=h("carol", Role.EDITOR)).status_code == 200
    assert [a["id"] for a in client.get("/approvals", headers=h("dave", Role.EDITOR)).json()] == []
    assert aid in [a["id"] for a in client.get("/approvals", headers=BOB).json()]


def test_snapshot_needs_group_wide_requester_and_approver(client, db):
    snap = {"action": "create_snapshot", "args": {"period": P}}
    assert client.post("/approvals", json=snap, headers=h("scoped_admin", Role.ADMIN, [1])).json()["verdict"] == "deny"
    aid = client.post("/approvals", json=snap, headers=ALICE).json()["approval"]["id"]
    assert decide(client, aid, "approve", headers=h("scoped_approver", Role.ADMIN, [1])).status_code == 403
    r = decide(client, aid, "approve").json()
    assert r["status"] == "executed" and "snapshot_id" in r["result"]
    assert db.scalar(select(ReportSnapshot.created_by)) == "bob"   # executed under the approver's identity


def test_failed_executor_rolls_back_partial_writes(client, db, monkeypatch):
    def boom(db_, req, args, approver):
        db_.add(OutboundMessage(approval_id=req.id, channel="email", company_code="IC1", subject="s", body="b"))
        db_.flush()
        raise RuntimeError("smtp password hunter2")
    monkeypatch.setitem(actions_mod.ACTIONS, "send_kpi_reminder",
                        dataclasses.replace(actions_mod.ACTIONS["send_kpi_reminder"], execute=boom))
    aid = submit(client).json()["approval"]["id"]
    r = decide(client, aid, "approve").json()
    assert r["status"] == "failed" and r["result"] == {"error": "RuntimeError"}   # type only, no message
    assert db.query(OutboundMessage).count() == 0


def test_execute_approved_refuses_anything_not_approved(client, db):
    aid = submit(client).json()["approval"]["id"]
    req = db.get(ApprovalRequest, aid)                       # still pending
    with pytest.raises(ApprovalError):
        execute_approved(db, req, Principal("bob", Role.ADMIN, None))
    assert db.query(OutboundMessage).count() == 0


def test_summary_counts_pending_for_other_admins_only(client):
    submit(client)
    assert client.get("/unread/summary", headers=BOB).json()["approvals_pending"] == 1
    assert client.get("/unread/summary", headers=ALICE).json()["approvals_pending"] == 0  # her own
    assert client.get("/unread/summary", headers=EDITOR).json()["approvals_pending"] == 0


# --- Copilot can only propose ---

def test_copilot_propose_action_files_a_request_and_runs_nothing(client, db):
    who = Principal("alice", Role.ADMIN, None)
    out = run_tool(db, who, "propose_action", {"action": "send_kpi_reminder", "reason": "Q2 gap",
                   "args": {"company_codes": ["IC1"], "period": P}}, session_id=None)
    assert out["verdict"] == "require_approval" and out["status"] == "pending" and "Not executed" in out["note"]
    req = db.get(ApprovalRequest, out["approval_id"])
    assert req.via == "copilot" and req.context == {"reason": "Q2 gap"}
    assert db.query(OutboundMessage).count() == 0


def test_copilot_cannot_bypass_policy_or_call_executors(client, db):
    who = Principal("alice", Role.ADMIN, None)
    bulk = run_tool(db, who, "propose_action", {"action": "send_kpi_reminder",
                    "args": {"company_codes": [f"IC{i}" for i in range(1, 9)], "period": P}})
    assert bulk["verdict"] == "deny" and db.query(OutboundMessage).count() == 0
    assert run_tool(db, who, "send_kpi_reminder", {"company_codes": ["IC1"]})["error"].startswith("unknown tool")
    assert "error" in run_tool(db, who, "propose_action", {"action": "format_disk", "args": {}})
    assert "error" in run_tool(db, who, "propose_action", {"action": "send_kpi_reminder", "args": {"period": "x"}})
    scoped = Principal("sam", Role.EDITOR, frozenset({1}))
    leak = run_tool(db, scoped, "propose_action", {"action": "send_kpi_reminder",
                    "args": {"company_codes": ["IC2"], "period": P}})
    assert leak["verdict"] == "deny"


def test_atomic_claim_stops_a_stale_second_decider(client, db, monkeypatch):
    """Two admins load 'pending' at once; only the first UPDATE ... WHERE status='pending' wins."""
    from app.approvals import service
    aid = submit(client).json()["approval"]["id"]
    assert decide(client, aid, "approve").json()["status"] == "executed"   # first admin wins
    real = db.get(ApprovalRequest, aid)
    stale = ApprovalRequest(id=aid, action=real.action, args=real.args, requested_by="alice",
                            risk=real.risk, summary="", via="api", status="pending")  # what admin #2 saw
    monkeypatch.setattr(db, "get", lambda model, ident: stale)
    with pytest.raises(ApprovalError) as e:
        service.decide(db, Principal("carol", Role.ADMIN, None), aid, "approve", None)
    assert e.value.status == 409
    assert db.query(OutboundMessage).count() == 1                          # still sent exactly once
