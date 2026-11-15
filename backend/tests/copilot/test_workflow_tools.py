"""Copilot workflow tools: list, save, and approval-gated run."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlalchemy import select

from app.assets import service as asset_service
from app.copilot.tools import run_tool
from app.core.security import Principal, Role, make_token
from app.db.models import Asset, WorkflowRun
from app.db.session import get_db
from app.main import app
from app.workflows import ops as wf_ops
from tests.api.conftest import client  # noqa: F401

P = "2026-10"

SIMPLE = {
    "title": "Group snapshot",
    "steps": [
        {
            "key": "card",
            "label": "Scorecard",
            "type": "scorecard",
            "args": {"scope": "group", "period": "run"},
        }
    ],
}


def h(user: str, role: Role = Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


ALICE = h("alice")
BOB = h("bob")
VIEWER = h("vic", Role.VIEWER, [1])


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def who(user="alice", role=Role.ADMIN, companies=None):
    return Principal(
        user_id=user,
        role=role,
        company_ids=None if companies is None else frozenset(companies),
    )


def test_list_workflows_requires_author(db):
    out = run_tool(db, who(role=Role.VIEWER, companies={1}), "list_workflows", {})
    assert "error" in out
    assert "Group-wide" in out["error"]


def test_list_and_save_workflow_via_tools(db):
    empty = run_tool(db, who(), "list_workflows", {})
    assert empty["count"] == 0 and empty["workflows"] == []

    saved = run_tool(
        db,
        who(),
        "save_workflow",
        {
            "key": "copilot_snapshot",
            "name": "Copilot snapshot",
            "description": "from chat",
            "definition": SIMPLE,
        },
    )
    assert saved.get("key") == "copilot_snapshot"
    assert saved.get("lifecycle") == "draft"

    listed = run_tool(db, who(), "list_workflows", {"include_artifact": True})
    assert listed["count"] == 1
    assert listed["workflows"][0]["key"] == "copilot_snapshot"
    assert listed["artifact"]["kind"] == "table"

    scoped = run_tool(db, who(role=Role.EDITOR, companies={1}), "save_workflow", {
        "key": "nope", "name": "Nope", "definition": SIMPLE,
    })
    assert "error" in scoped


def test_run_workflow_precheck_and_approve_queues_execute(client, db):
    # Save + validate + publish via API helpers shared with UI
    created = client.post(
        "/workflows/defs",
        headers=ALICE,
        json={"key": "run_me", "name": "Run me", "definition": SIMPLE},
    )
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    v = client.post("/workflows/defs/run_me/validate", headers=ALICE).json()
    assert v["validation"]["ok"], v

    prop = client.post(
        "/approvals",
        json={"action": "publish_asset", "args": {"asset_id": aid}},
        headers=ALICE,
    )
    assert prop.status_code == 201
    assert (
        client.post(
            f"/approvals/{prop.json()['approval']['id']}/decision",
            json={"decision": "approve"},
            headers=BOB,
        ).json()["status"]
        == "executed"
    )

    # Unpublished / unknown fails precheck
    bad = client.post(
        "/approvals",
        json={"action": "run_workflow", "args": {"key": "missing", "period": P}},
        headers=ALICE,
    )
    assert bad.status_code == 422

    # Propose run from chat path (approvals API)
    proposed = client.post(
        "/approvals",
        json={
            "action": "run_workflow",
            "args": {"key": "run_me", "period": P},
            "context": {"reason": "Need this period's snapshot"},
        },
        headers=ALICE,
    )
    assert proposed.status_code == 201
    body = proposed.json()
    assert body["verdict"] == "require_approval"
    aid_run = body["approval"]["id"]

    with patch("app.workflows.ops.queue_execute") as q:
        decided = client.post(
            f"/approvals/{aid_run}/decision",
            json={"decision": "approve"},
            headers=BOB,
        )
        assert decided.status_code == 200
        body = decided.json()
        assert body["status"] == "executed", body
        assert body["result"]["queued"] is True
        assert body["result"]["run"]["workflow"] == "def:run_me"
        assert body["result"]["run"]["period"] == P
        assert body["result"]["run"]["requested_by"] == "alice"
        # Background thread may still be polling; give it a moment to call queue_execute.
        import time

        for _ in range(50):
            if q.called:
                break
            time.sleep(0.02)
        assert q.called

    db.expire_all()
    runs = list(db.scalars(select(WorkflowRun).where(WorkflowRun.workflow == "def:run_me")))
    assert len(runs) == 1
    assert runs[0].period == P


def test_ops_require_author_and_resolve_unpublished(db):
    assert wf_ops.require_author(who(role=Role.VIEWER)) is not None
    assert wf_ops.require_author(who()) is None

    a = asset_service.create(
        db, who(), "workflow", "draft_only", "Draft only", "", SIMPLE
    )
    assert a.published_version is None
    with pytest.raises(wf_ops.WorkflowOpsError, match="not published"):
        wf_ops.resolve_run_version(db, who(), "draft_only", allow_draft=False)

    # Admin allow_draft resolves latest version
    asset, version, _wf = wf_ops.resolve_run_version(
        db, who(), "draft_only", allow_draft=True
    )
    assert asset.key == "draft_only" and version == 1


def test_propose_action_run_workflow_via_copilot_tool(db):
    asset_service.create(db, who(), "workflow", "via_tool", "Via tool", "", SIMPLE)
    # Must be published for precheck — mark published directly for unit speed
    a = db.query(Asset).filter_by(key="via_tool").one()
    a.published_version = 1
    a.lifecycle = "published"
    db.commit()

    out = run_tool(
        db,
        who(),
        "propose_action",
        {
            "action": "run_workflow",
            "args": {"key": "via_tool", "period": P},
            "reason": "from copilot",
        },
    )
    assert out.get("verdict") == "require_approval"
    assert out.get("approval_id")
    assert "Not executed" in (out.get("note") or "")
