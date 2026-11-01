"""CHRO workflow asset definitions (OE People workflows adapted to AC WorkflowSpec)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import service as asset_service
from app.core.security import Principal
from app.db.models import Asset, AssetVersion

_EXEC_VOICE = (
    " Audience: Group CHRO / C-suite. Short scannable markdown (H2 + bullets). "
    "Human pillar and KPI names only — never snake_case, backticks, tool names, "
    "JSON, synthetic data, or mock/fixture language. Charts on the page carry detail; "
    "do not restate every number. Do not invent figures."
)

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
                    "label": "Group scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "CHRO cycle guidance",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "inputs": ["card"],
                        "message": (
                            "Recommend a performance-review operating cadence for the ICs using "
                            "the scorecard in context. At most 8 bullets: which ICs need coaching, "
                            "KRA / mid-term focus, and one next action."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Executive summary",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro"],
                        "instructions": (
                            "Decision brief for Group CHRO: status of Performance Management, "
                            "ICs to coach this cycle, and the ask. Max 6 bullets."
                        ),
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
                        "inputs": ["card"],
                        "message": (
                            "Advise on a mid-year compensation refresh. Cite Retention and Talent "
                            "Management scores from the scorecard. Stay qualitative on pay bands "
                            "and dollar amounts — no invented financials. Max 6 bullets."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "cfo",
                    "label": "CFO envelope",
                    "type": "agent",
                    "args": {
                        "key": "cfo",
                        "inputs": ["card", "chro"],
                        "message": (
                            "Given the CHRO advice, outline a people-cost envelope and approval "
                            "gates for Group CHRO + CFO. No invented financials. Max 5 bullets."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Joint recommendation",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro", "cfo"],
                        "instructions": (
                            "Propose-only joint recommendation for Group CHRO + CFO: decision ask, "
                            "retention signal, and gates. Max 6 bullets."
                        ),
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
                    "key": "card",
                    "label": "Group scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "CHRO structure options",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "inputs": ["card"],
                        "message": (
                            "Draft three org-design options for L&T Group People (IC HRBP coverage "
                            "and Group centres of excellence). Propose-only; no headcount cuts. "
                            "Use scorecard pressure points only as context — no invented headcount. "
                            "Short sections: problem, options A/B/C (one line each), preferred."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "cfo",
                    "label": "Cost implications",
                    "type": "agent",
                    "args": {
                        "key": "cfo",
                        "inputs": ["card", "chro"],
                        "message": (
                            "Comment on cost and sequencing risks of the CHRO org options. "
                            "No invented financials. Max 5 bullets."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Decision brief",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro", "cfo"],
                        "instructions": (
                            "One decision brief: preferred option, why, open questions. Max 6 bullets."
                        ),
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
                    "key": "card",
                    "label": "Group scorecard",
                    "type": "scorecard",
                    "args": {"scope": "group", "period": "run"},
                },
                {
                    "key": "chro",
                    "label": "Role scorecard",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "inputs": ["card"],
                        "message": (
                            "Produce an executive search brief for an IC CHRO or critical People "
                            "leader at L&T Group. Tie year-one outcomes to Group HR Scorecard pillars "
                            "in context. Short sections: role in one paragraph, why now (max 5 "
                            "bullets), year-one outcomes (table or bullets). No invented measures."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Search pack",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro"],
                        "instructions": (
                            "Search pack for hiring committee: mission, year-one outcomes, "
                            "must-haves, process. Max 8 bullets."
                        ),
                    },
                },
            ],
        },
    },
    {
        "key": "chro_morning_brief",
        "name": "CHRO morning brief",
        "description": "Daily pulse: group scorecard + workforce risks + draft decisions.",
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
                    "key": "pulse",
                    "label": "Workforce pulse",
                    "type": "tool",
                    "args": {"name": "get_workforce_pulse", "args": {}},
                },
                {
                    "key": "drafts",
                    "label": "Draft actions",
                    "type": "tool",
                    "args": {"name": "list_draft_actions", "args": {}},
                },
                {
                    "key": "chro",
                    "label": "Priorities",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "inputs": ["card", "pulse", "drafts"],
                        "message": (
                            "Write a morning brief for the Group CHRO using the scorecard, pulse, "
                            "and draft actions in context. Exactly three short sections: "
                            "(1) Top risks (2) Calls to make (3) Decisions ready. "
                            "At most 3 bullets each."
                            + _EXEC_VOICE
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
                        "inputs": ["card"],
                        "message": (
                            "Facilitate a People department check-in using the scorecard: what "
                            "moved, which pillars need attention, and what to propose next. "
                            "Max 8 bullets."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Check-in brief",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "chro"],
                        "instructions": (
                            "Short check-in note for the People leadership team: status, risks, "
                            "next proposes. Max 6 bullets."
                        ),
                    },
                },
            ],
        },
    },
    {
        "key": "weekly_workforce_brief",
        "name": "Weekly workforce briefing",
        "description": "Scorecard + pulse/skills/succession/drafts with a board-ready CHRO brief.",
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
                    "key": "pulse",
                    "label": "Workforce pulse",
                    "type": "tool",
                    "args": {"name": "get_workforce_pulse", "args": {}},
                },
                {
                    "key": "skills",
                    "label": "Skills gap",
                    "type": "tool",
                    "args": {"name": "get_skills_gap", "args": {}},
                },
                {
                    "key": "succession",
                    "label": "Succession bench",
                    "type": "tool",
                    "args": {"name": "get_succession_bench", "args": {}},
                },
                {
                    "key": "drafts",
                    "label": "Draft actions",
                    "type": "tool",
                    "args": {"name": "list_draft_actions", "args": {}},
                },
                {
                    "key": "chro",
                    "label": "Workforce synthesis",
                    "type": "agent",
                    "args": {
                        "key": "chro",
                        "inputs": ["card", "pulse", "skills", "succession", "drafts"],
                        "message": (
                            "Compose a weekly workforce note for the Group CHRO using the "
                            "scorecard and workforce outputs already in context. Rank top issues, "
                            "name draft actions ready for approval, and stay propose-only — never "
                            "claim an action was executed. Max 8 bullets."
                            + _EXEC_VOICE
                        ),
                    },
                },
                {
                    "key": "summary",
                    "label": "Board-ready brief",
                    "type": "summarize",
                    "args": {
                        "inputs": ["card", "pulse", "skills", "succession", "drafts", "chro"],
                        "instructions": (
                            "Board-ready weekly brief: scorecard exceptions, recommended approvals "
                            "this week, and 90-day monitors after approval. Max 6 bullets. Lead "
                            "with the decision ask."
                        ),
                    },
                },
            ],
        },
    },
]


def seed_chro_workflows(db: Session, who: Principal) -> int:
    """Idempotently create + validate + publish CHRO workflow assets as builtin.

    When the fixture definition drifts (e.g. agent inputs wired to scorecard), push a new
    builtin version and re-publish so demo runs pick up the fix without a manual republish.
    """
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
            definition = asset_service.parse_definition("workflow", spec["definition"]).model_dump()
            row = asset_service.latest(db, a)
            if row.definition != definition:
                a.version += 1
                a.name = spec["name"]
                a.description = spec["description"]
                db.add(
                    AssetVersion(
                        asset_id=a.id,
                        version=a.version,
                        definition=definition,
                        created_by=who.user_id,
                    )
                )
                a.lifecycle = asset_service.lifecycle_of(a)
                db.commit()
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
