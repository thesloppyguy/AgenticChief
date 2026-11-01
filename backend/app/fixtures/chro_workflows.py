"""CHRO workflow asset definitions (OE People workflows adapted to AC WorkflowSpec)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import service as asset_service
from app.core.security import Principal, Role
from app.db.models import Asset

CHRO_WORKFLOWS: list[dict] = [
    {
        "key": "performance_review",
        "name": "Performance review cycle",
        "description": "Pull Performance Management pillar, ask CHRO for cycle guidance, summarise actions.",
        "definition": {
            "title": "Performance review cycle",
            "steps": [
                {
                    "key": "card",
                    "label": "Performance pillar scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "CHRO cycle guidance",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Using the group scorecard in context, recommend a performance-review "
                            "operating cadence for the ICs. Call out KRA / mid-term due months and "
                            "which ICs need coaching. Do not invent KPI numbers."
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Executive summary",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro"],
                        "instructions": "Produce a one-page CHRO brief: status, risks, next actions.",
                    },
                },
            ],
        },
    },
    {
        "key": "comp_refresh",
        "name": "Compensation refresh",
        "description": "CHRO + CFO view on bands vs retention pressure from the scorecard.",
        "definition": {
            "title": "Compensation refresh",
            "steps": [
                {
                    "key": "card",
                    "label": "Group scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "CHRO market read",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Advise on a mid-year compensation refresh. Use retention and talent "
                            "management signals from the scorecard. Stay qualitative on pay numbers."
                        ),
                    },
                },
                {
                    "key": "cfo",
                    "label": "CFO envelope",
                    "type": "agent",
                    "args": {
                        "key": "cfo",
                        "message": (
                            "Given the CHRO advice, outline a people-cost envelope and approval gates "
                            "for a Group CHRO. Do not invent financials not in context."
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Joint recommendation",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro", "cfo"],
                        "instructions": "Merge into a propose-only recommendation for Group CHRO + CFO.",
                    },
                },
            ],
        },
    },
    {
        "key": "org_design",
        "name": "Org design review",
        "description": "CHRO (+ CFO) org-design memo for an IC or Group People structure.",
        "definition": {
            "title": "Org design review",
            "steps": [
                {
                    "key": "chro",
                    "label": "CHRO structure options",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Draft an org-design options memo for L&T Group People covering IC HRBP "
                            "coverage and Group centres of excellence. Propose-only; no headcount cuts."
                        ),
                    },
                },
                {
                    "key": "cfo",
                    "label": "Cost implications",
                    "type": "agent",
                    "args": {
                        "key": "cfo",
                        "message": "Comment on cost and sequencing risks of the CHRO org options.",
                    },
                },
                {
                    "key": "summary",
                    "label": "Decision brief",
                    "type": "summarize",
                    "args": {
                        "inputs": ["chro", "cfo"],
                        "instructions": "One decision brief with preferred option and open questions.",
                    },
                },
            ],
        },
    },
    {
        "key": "exec_search_brief",
        "name": "Executive search brief",
        "description": "CHRO role-scorecard style brief for a critical leadership hire.",
        "definition": {
            "title": "Executive search brief",
            "steps": [
                {
                    "key": "chro",
                    "label": "Role scorecard",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Produce an executive search brief for an IC CHRO or critical People leader "
                            "at L&T Group. Include year-one outcomes tied to the Group HR Scorecard."
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Search pack",
                    "type": "summarize",
                    "args": {
                        "inputs": ["chro"],
                        "instructions": "Format as a search pack: mission, outcomes, must-haves, process.",
                    },
                },
            ],
        },
    },
    {
        "key": "chro_morning_brief",
        "name": "CHRO morning brief",
        "description": "Daily pulse: group scorecard + at-risk goals narrative.",
        "definition": {
            "title": "CHRO morning brief",
            "steps": [
                {
                    "key": "card",
                    "label": "Today's scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "Priorities",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Write a short morning brief for the Group CHRO: top risks, ICs to call, "
                            "and whether to propose KPI reminders. Use only scorecard facts."
                        ),
                    },
                },
            ],
        },
    },
    {
        "key": "department_check_in",
        "name": "People department check-in",
        "description": "People dept check-in vs scorecard pillars.",
        "definition": {
            "title": "People department check-in",
            "steps": [
                {
                    "key": "card",
                    "label": "Group scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "Check-in notes",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Facilitate a People department check-in: what moved since last month, "
                            "which goals are at_risk/off_track, and what to propose next."
                        ),
                    },
                },
            ],
        },
    },
    {
        "key": "weekly_workforce_brief",
        "name": "Weekly workforce briefing",
        "description": "Scorecard + CHRO narrative of pulse risks and draft actions (propose-only).",
        "definition": {
            "title": "Weekly workforce briefing",
            "steps": [
                {
                    "key": "card",
                    "label": "Group scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "Workforce synthesis",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "message": (
                            "Compose a weekly workforce briefing for the Group CHRO. Use the scorecard "
                            "in context for pillar status. Call get_workforce_pulse, get_skills_gap, "
                            "get_succession_bench, and list_draft_actions if available; otherwise stay "
                            "with scorecard facts. Rank top issues, name draft actions ready for "
                            "propose_action, and do not invent KPI or fixture numbers. Propose-only — "
                            "never claim an action was executed."
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Board-ready brief",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro"],
                        "instructions": (
                            "One-page weekly brief: pulse, scorecard exceptions, recommended "
                            "approvals this week, and 90-day monitors to arm after approval."
                        ),
                    },
                },
            ],
        },
    },
]


def seed_chro_workflows(db: Session, who: Principal) -> int:
    """Idempotently create + validate + publish CHRO workflow assets as builtin."""
    created = 0
    for spec in CHRO_WORKFLOWS:
        existing = db.scalar(select(Asset).where(Asset.kind == "workflow", Asset.key == spec["key"]))
        if existing is None:
            a = asset_service.create(
                db,
                who,
                "workflow",
                spec["key"],
                spec["name"],
                spec["description"],
                spec["definition"],
                builtin=True,
            )
            created += 1
        else:
            a = existing
        try:
            asset_service.validate(db, who, a)
        except Exception:
            db.rollback()
            continue
        a = asset_service.get(db, "workflow", spec["key"])
        row = asset_service.latest(db, a)
        if a.published_version != a.version and row.validated:
            # Bypass four-eyes for demo seed builtins.
            a.published_version = a.version
            a.lifecycle = asset_service.lifecycle_of(a)
            db.commit()
    return created
