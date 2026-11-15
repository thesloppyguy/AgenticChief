"""Chat tools attach UI cards only when include_artifact=true."""
from __future__ import annotations

from app.copilot.tools import run_tool
from app.core.security import Principal, Role
from app.db.session import get_db
from app.main import app
from app.workforce.tools import want_artifact
from tests.api.conftest import client  # noqa: F401


def test_want_artifact_defaults_false():
    assert want_artifact(None) is False
    assert want_artifact({}) is False
    assert want_artifact({"include_artifact": False}) is False
    assert want_artifact({"include_artifact": True}) is True
    assert want_artifact({"include_artifact": "true"}) is True


def test_group_score_prose_by_default(client):
    db = next(app.dependency_overrides[get_db]())
    who = Principal("u1", Role.ADMIN, None)
    bare = run_tool(db, who, "get_group_score", {"period": "2026-11"})
    assert "artifact" not in bare

    with_art = run_tool(
        db, who, "get_group_score", {"period": "2026-11", "include_artifact": True}
    )
    assert with_art.get("artifact", {}).get("kind") == "scorecard_summary"


def test_tool_schemas_expose_include_artifact():
    from app.copilot.tools import TOOLS

    for name in (
        "get_group_score",
        "get_ic_score",
        "explain_pillar",
        "rank_ics",
        "get_workforce_pulse",
        "list_draft_actions",
    ):
        tool = next(t for t in TOOLS if t["name"] == name)
        assert "include_artifact" in tool["input_schema"]["properties"]
