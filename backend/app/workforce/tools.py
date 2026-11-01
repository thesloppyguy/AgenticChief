"""Executive/copilot tools for fixture-backed workforce intelligence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.security import Principal
from app.workforce import loader

WORKFORCE_TOOLS: list[dict[str, Any]] = sorted(
    [
        {
            "name": "get_workforce_pulse",
            "description": "Group workforce briefing pulse: headcount, skill gap, internal fill, "
            "succession thinness, EX index, and top ranked issues. Demo fixture numbers "
            "(not the live scorecard KPI engine). Prefer this for 'what's the weekly brief'.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_skills_gap",
            "description": "Future-skills demand vs supply by domain, build-vs-buy, and internal "
            "mobility adjacency. Fixture-backed; do not invent domain counts.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_succession_bench",
            "description": "Succession coverage by function and critical-role bench readiness. "
            "Fixture-backed.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_draft_actions",
            "description": "List draft company-wide CHRO actions (capability build, retention "
            "corrective) ready to propose via propose_action. Returns keys, recipients, ROI.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Optional draft key e.g. capability_green_h2",
                    }
                },
            },
        },
    ],
    key=lambda t: t["name"],
)

_WORKFORCE_NAMES = {t["name"] for t in WORKFORCE_TOOLS}


def is_workforce_tool(name: str) -> bool:
    return name in _WORKFORCE_NAMES


def dispatch(name: str, args: dict, db: Session, who: Principal) -> dict:
    del db, who  # fixture-backed; principal reserved for future scoping
    if name == "get_workforce_pulse":
        data = loader.pulse()
        return {**data, "artifact": loader.artifact_for("pulse", data)}
    if name == "get_skills_gap":
        data = loader.skills()
        return {**data, "artifact": loader.artifact_for("skills", data)}
    if name == "get_succession_bench":
        data = loader.succession()
        return {**data, "artifact": loader.artifact_for("succession", data)}
    if name == "list_draft_actions":
        data = loader.draft_actions()
        key = (args.get("key") or "").strip()
        drafts = data.get("drafts") or []
        if key:
            drafts = [d for d in drafts if d.get("key") == key]
        out = {"drafts": drafts, "artifact": loader.artifact_for("actions", {"drafts": drafts})}
        return out
    return {"error": f"unknown workforce tool {name}"}
