"""Home dashboard layout: GET default, apply via approval, personal scope."""
from __future__ import annotations

import pytest

from app.core.security import Role, make_token
from app.dashboard import layout as layout_service
from app.db.models import DashboardLayout
from app.db.session import get_db
from app.main import app
from tests.api.conftest import client  # noqa: F401


def h(user: str, role: Role = Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE = h("alice")
BOB = h("bob")


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def _hide_brief_layout(widgets=None):
    sections = [
        {"key": "brief", "visible": False},
        {"key": "pulse", "visible": True},
        {"key": "scorecard", "visible": True},
        {"key": "exception", "visible": True},
        {"key": "issues", "visible": True},
        {"key": "pinned_widgets", "visible": True},
    ]
    return {"sections": sections, "widgets": widgets or []}


def test_get_layout_returns_default_when_empty(client):
    r = client.get("/dashboard/layout", headers=ALICE)
    assert r.status_code == 200
    body = r.json()
    assert [s["key"] for s in body["sections"]] == list(layout_service.SECTION_KEYS)
    assert all(s["visible"] for s in body["sections"])
    assert body["widgets"] == []
    assert body["pulse_cells"] == []
    assert body["pulse_hidden"] == []
    assert {s["key"] for s in body["pulse_sources"]} == set(layout_service.PULSE_SOURCES)


def test_apply_layout_persists_for_user(db):
    payload = layout_service.parse_layout(_hide_brief_layout())
    out = layout_service.apply_layout(db, "alice", payload)
    db.commit()
    assert out["sections"][0] == {"key": "brief", "visible": False}
    row = db.get(DashboardLayout, "alice")
    assert row is not None and row.sections[0]["visible"] is False
    assert db.get(DashboardLayout, "bob") is None


def test_precheck_rejects_noop_and_bad_keys(db):
    default = layout_service.default_layout()
    with pytest.raises(ValueError, match="matches what is already"):
        from app.approvals.actions import UpdateDashboardLayoutArgs, _precheck_dashboard_layout
        from app.core.security import Principal

        who = Principal(user_id="alice", role=Role.ADMIN, company_ids=None)
        _precheck_dashboard_layout(
            db, who, UpdateDashboardLayoutArgs(**default)
        )

    with pytest.raises(ValueError, match="unknown section"):
        layout_service.parse_layout(
            {"sections": [{"key": "not_a_section", "visible": True}], "widgets": []}
        )


def test_approval_execute_writes_requester_layout(client, db):
    widget = {
        "id": "w1",
        "title": "Pulse chart",
        "kind": "workforce_pulse",
        "artifact": {"kind": "workforce_pulse", "title": "Pulse chart", "items": []},
    }
    args = _hide_brief_layout(widgets=[widget])
    proposed = client.post(
        "/approvals",
        json={
            "action": "update_dashboard_layout",
            "args": args,
            "context": {"reason": "Hide brief and pin pulse"},
        },
        headers=ALICE,
    )
    assert proposed.status_code == 201
    body = proposed.json()
    assert body["verdict"] == "require_approval"
    assert body["approval"]["status"] == "pending"
    changes = body["approval"].get("context") or {}
    assert "Hide brief" in " ".join(changes.get("changes") or [])
    aid = body["approval"]["id"]

    # Still default until approved
    assert client.get("/dashboard/layout", headers=ALICE).json()["sections"][0]["visible"] is True

    decided = client.post(
        f"/approvals/{aid}/decision",
        json={"decision": "approve"},
        headers=BOB,
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "executed"

    alice_layout = client.get("/dashboard/layout", headers=ALICE).json()
    assert alice_layout["sections"][0]["visible"] is False
    assert len(alice_layout["widgets"]) == 1
    assert alice_layout["widgets"][0]["id"] == "w1"

    # Personal: Bob unchanged
    bob_layout = client.get("/dashboard/layout", headers=BOB).json()
    assert bob_layout["widgets"] == []
    assert bob_layout["sections"][0]["visible"] is True


def test_diff_layout_summarizes_pin_and_hide():
    before = layout_service.default_layout()
    after = layout_service.parse_layout(
        _hide_brief_layout(
            widgets=[
                {
                    "id": "w1",
                    "title": "Skills",
                    "kind": "skills_demand_supply",
                    "artifact": {"kind": "skills_demand_supply"},
                }
            ]
        )
    )
    changes = layout_service.diff_layout(before, after)
    assert any("Hide brief" in c for c in changes)
    assert any("Pin widget" in c and "Skills" in c for c in changes)


def test_requester_may_self_approve_personal_layout(client, db):
    """Home layout is personal — four-eyes does not block the requester."""
    args = {
        "sections": [{"key": k, "visible": True} for k in layout_service.SECTION_KEYS],
        "widgets": [],
        "pulse_cells": [
            {
                "id": "pc1",
                "key": "pending_actions",
                "label": "Pending actions",
                "source": "pending_approvals",
            }
        ],
        "pulse_hidden": [],
    }
    proposed = client.post(
        "/approvals",
        json={"action": "update_dashboard_layout", "args": args},
        headers=ALICE,
    )
    assert proposed.status_code == 201
    body = proposed.json()
    assert body["approval"]["allow_self_approval"] is True
    aid = body["approval"]["id"]

    # Same user who proposed can approve
    decided = client.post(
        f"/approvals/{aid}/decision",
        json={"decision": "approve"},
        headers=ALICE,
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "executed"
    layout = client.get("/dashboard/layout", headers=ALICE).json()
    assert layout["pulse_cells"][0]["key"] == "pending_actions"


def test_approval_adds_pulse_kpi_and_pulse_api_merges_it(client, db):
    from app.db.models import ApprovalRequest

    db.add(
        ApprovalRequest(
            action="send_kpi_reminder",
            risk="external_message",
            summary="seed pending",
            args={},
            status="pending",
            requested_by="carol",
            via="api",
        )
    )
    db.commit()

    args = {
        **_hide_brief_layout(),
        "sections": [
            {"key": k, "visible": True} for k in layout_service.SECTION_KEYS
        ],
        "pulse_cells": [
            {
                "id": "pc_pending",
                "key": "pending_actions",
                "label": "Pending actions",
                "source": "pending_approvals",
                "note": "awaiting approval",
                "tone": "alert",
            }
        ],
        "pulse_hidden": [],
    }
    proposed = client.post(
        "/approvals",
        json={
            "action": "update_dashboard_layout",
            "args": args,
            "context": {"reason": "Add pending-actions pulse KPI"},
        },
        headers=ALICE,
    )
    assert proposed.status_code == 201
    changes = " ".join((proposed.json()["approval"].get("context") or {}).get("changes") or [])
    assert "Add pulse KPI" in changes and "Pending actions" in changes
    aid = proposed.json()["approval"]["id"]

    before_pulse = client.get("/workforce/pulse", headers=ALICE).json()
    assert not any(c.get("key") == "pending_actions" for c in before_pulse.get("cells") or [])

    decided = client.post(
        f"/approvals/{aid}/decision",
        json={"decision": "approve"},
        headers=BOB,
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "executed"

    layout = client.get("/dashboard/layout", headers=ALICE).json()
    assert len(layout["pulse_cells"]) == 1
    assert layout["pulse_cells"][0]["source"] == "pending_approvals"

    pulse = client.get("/workforce/pulse", headers=ALICE).json()
    cell = next(c for c in pulse["cells"] if c.get("key") == "pending_actions")
    assert cell["label"] == "Pending actions"
    assert cell["personal"] is True
    assert cell["value"] >= 1  # at least the seed pending from carol

    # Personal: Bob does not get Alice's pulse KPI
    bob_pulse = client.get("/workforce/pulse", headers=BOB).json()
    assert not any(c.get("key") == "pending_actions" for c in bob_pulse.get("cells") or [])
