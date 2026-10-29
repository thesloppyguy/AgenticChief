"""Skills and an agent that ship with the platform (the PRD's examples). Published at install: they are
reviewed code, not user-authored. They cannot be edited; copy one under a new key to change it."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, Role
from app.db.models import Asset, AssetVersion
from app.kpi_registry.seed import PILLAR_WEIGHTS

from . import service

SYSTEM = Principal("system", Role.ADMIN, None)
PERIOD = {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$", "description": "Fiscal period, YYYY-MM"}

SKILLS = {
    "missing_submissions": ("Identify missing KPI submissions",
        "Which companies have not provided KPI data for a period, and which KPIs have no source at all.",
        {"instructions": ("Find missing KPI submissions for {period}. Call list_missing_submissions. Group the results by KPI, "
                          "name the companies, and give the count for each. Report the KPIs listed under no_source_kpis "
                          "separately: those are connection gaps, not submissions anyone owes. Finish with the three KPIs "
                          "that most need chasing."),
         "inputs": {"type": "object", "properties": {"period": PERIOD}, "required": ["period"]},
         "tools": ["list_missing_submissions", "get_group_score"]}),
    "compare_companies": ("Compare company performance",
        "Rank the companies at one end of the scorecard and say what is driving their scores.",
        {"instructions": ("Compare the {order} {limit} companies for {period}. Call rank_ics, then get_ic_score for the "
                          "two at the extreme end. Say what is driving each score (weakest pillars, excluded KPIs) and "
                          "whether anything common links them. Mention each company's coverage."),
         "inputs": {"type": "object", "properties": {"period": PERIOD, "order": {"type": "string", "enum": ["lowest", "highest"], "default": "lowest"},
                                                      "limit": {"type": "integer", "minimum": 3, "maximum": 20, "default": 10}},
                    "required": ["period"]},
         "tools": ["rank_ics", "get_ic_score", "get_group_score"]}),
    "pillar_investigation": ("Investigate a pillar",
        "Explain a pillar's performance: which KPIs drive it, how coverage affects it, and which companies lag.",
        {"instructions": ("Investigate the {pillar} pillar for {period}. Call explain_pillar. Say which sub-KPIs pull the "
                          "score down, how many companies each is based on, and which companies are weakest. Use "
                          "search_documents if you need the KPI's definition. Separate facts from your interpretation."),
         "inputs": {"type": "object", "properties": {"period": PERIOD, "pillar": {"type": "string", "enum": list(PILLAR_WEIGHTS)}},
                    "required": ["period", "pillar"]},
         "tools": ["explain_pillar", "get_group_score", "rank_ics", "search_documents"]}),
    "monthly_review_brief": ("Brief me on the monthly review",
        "A short leadership briefing built from the latest completed monthly review.",
        {"instructions": ("Brief me on the monthly review for {period}. Call latest_monthly_review. Give the headline, the "
                          "two things that need attention, and the caveats that limit how far the numbers can be trusted. "
                          "If there is no completed review, say so and suggest generating one. Mention whether it has "
                          "been published."),
         "inputs": {"type": "object", "properties": {"period": PERIOD}, "required": ["period"]},
         "tools": ["latest_monthly_review", "get_group_score", "search_documents"]}),
}

AGENTS = {
    "hr_analyst": ("HR Analytics",
        "A precise analyst for scorecard questions.",
        {"instructions": ("Answer as a careful HR analyst. Lead with the answer, then the evidence from tool results. State coverage "
                          "and exclusions every time you quote a score, and keep facts separate from interpretation."),
         "tools": ["explain_pillar", "get_group_score", "get_ic_score", "latest_monthly_review", "list_missing_submissions",
                   "rank_ics", "search_documents"]}),
}


def seed_builtin(db: Session) -> int:
    n = 0
    for kind, table in (("skill", SKILLS), ("agent", AGENTS)):
        for key, (name, description, definition) in table.items():
            if db.scalar(select(Asset.id).where(Asset.kind == kind, Asset.key == key)):
                continue
            a = service.create(db, SYSTEM, kind, key, name, description, definition, builtin=True)
            service.validate(db, SYSTEM, a)
            assert a.validated_version == 1, f"built-in {kind} {key} failed validation: {a.validation}"
            a.published_version = 1
            a.lifecycle = service.lifecycle_of(a)
            row = db.scalar(select(AssetVersion).where(AssetVersion.asset_id == a.id, AssetVersion.version == 1))
            row.validated = True
            db.commit()
            n += 1
    return n
