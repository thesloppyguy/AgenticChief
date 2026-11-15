"""Copilot tools for Home layout + scorecard config drafts."""
from __future__ import annotations

from app.copilot import tools as copilot_tools
from app.core.security import Principal, Role, make_token
from app.db.session import get_db
from app.main import app
from tests.api.conftest import client  # noqa: F401


def h(user="alice", role=Role.ADMIN, companies=None):
    return {"Authorization": f"Bearer {make_token(user, role, companies)}"}


def _who(user="alice", role=Role.ADMIN, companies=None):
    return Principal(user_id=user, role=role, company_ids=companies)


def test_get_dashboard_layout_tool(client):
    db = next(app.dependency_overrides[get_db]())
    try:
        out = copilot_tools.run_tool(db, _who(), "get_dashboard_layout", {})
        assert "sections" in out and "pulse_cells" in out
        assert out["pulse_cells"] == []
        assert {s["key"] for s in out["pulse_sources"]} >= {"pending_approvals", "draft_chro_actions"}
    finally:
        db.close()


def test_get_scorecard_config_tool(client):
    db = next(app.dependency_overrides[get_db]())
    try:
        out = copilot_tools.run_tool(db, _who(), "get_scorecard_config", {})
        assert out["version"] == 1
        assert len(out["kpis"]) == 23
        assert all("weight" in k and "target" in k for k in out["kpis"])
    finally:
        db.close()


def test_draft_scorecard_config_admin_gate_and_happy_path(client):
    db = next(app.dependency_overrides[get_db]())
    try:
        denied = copilot_tools.run_tool(
            db,
            _who(role=Role.VIEWER, companies=[1]),
            "draft_scorecard_config",
            {"rules": {"kpi_overrides": {"kra_submission": {"target": 95}}}},
        )
        assert "error" in denied and "admin" in denied["error"].lower()

        out = copilot_tools.run_tool(
            db,
            _who(),
            "draft_scorecard_config",
            {
                "rules": {
                    "kpi_overrides": {"gptw_score": {"weight": 0.40}},
                    "added_kpis": [
                        {
                            "key": "board_readiness",
                            "label": "Board readiness index",
                            "pillar": "engagement_wellness",
                            "weight": 0.10,
                            "target": 80,
                            "direction": "higher",
                        }
                    ],
                },
                "note": "Add board readiness",
            },
        )
        assert out.get("version") == 2
        assert "kpi.board_readiness.added" in out["diff"]
        assert "next" in out and "activate_scorecard_config" in out["next"]
    finally:
        db.close()


def test_tools_catalogue_includes_dashboard_and_scorecard(client):
    names = {t["name"] for t in copilot_tools.TOOLS}
    assert {"get_dashboard_layout", "get_scorecard_config", "draft_scorecard_config"} <= names
