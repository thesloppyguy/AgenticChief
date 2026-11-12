"""Executive/copilot tools for fixture-backed workforce intelligence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.security import Principal
from app.workforce import loader

_IC_CODE_PROP = {
    "type": "string",
    "description": "Independent Company code, e.g. LTIM, LTTS, LTF, LTMR, LTR. "
    "Omit for Group totals. Resolve 'LTIMindtree' / 'LNT Mindtree' → LTIM.",
}

_PULSE_SCHEMA = {
    "type": "object",
    "properties": {
        "company_code": _IC_CODE_PROP,
    },
}

_SUCCESSION_FOCUS_PROP = {
    "type": "string",
    "enum": ["overview", "weak_gaps", "c_suite", "bench"],
    "description": "Which chart to attach for this answer. "
    "overview = coverage-by-function dashboard (default for get_succession_coverage). "
    "weak_gaps = roles with thin / no successor (use for 'which roles lack successors'). "
    "c_suite = C-level / Chief roles only. "
    "bench = full critical-role bench table (default for get_succession_bench). "
    "Always set focus to match the question — do not reuse overview for narrow asks.",
}

_SUCCESSION_SCHEMA = {
    "type": "object",
    "properties": {
        "company_code": _IC_CODE_PROP,
        "period": {
            "type": "string",
            "description": "YYYY-MM period for freshness check against fixture as_of. "
            "Optional; defaults to the run period.",
        },
        "focus": _SUCCESSION_FOCUS_PROP,
    },
}

WORKFORCE_TOOLS: list[dict[str, Any]] = sorted(
    [
        {
            "name": "get_workforce_pulse",
            "description": "Workforce briefing pulse for Group or one IC: headcount, skill gap, "
            "internal fill, succession thinness, EX index, and top ranked issues with "
            "company_codes and draft action_key when ready. Demo fixture numbers "
            "(not the live scorecard KPI engine). Prefer this for 'what's the weekly brief'.",
            "input_schema": _PULSE_SCHEMA,
        },
        {
            "name": "get_skills_gap",
            "description": "Future-skills demand vs supply by domain, build-vs-buy, and internal "
            "mobility adjacency. Fixture-backed; do not invent domain counts.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_succession_coverage",
            "description": "Succession coverage for Group or one IC: critical roles, nominated "
            "successors with readiness (ready_now / ready_1_2y / no_ready), 9-box, incumbent "
            "flight-risk, and vacancy exposure. Fixture-backed. Pass focus to choose the chart: "
            "overview (by-function dashboard), weak_gaps, c_suite, or bench. "
            "Do NOT substitute Talent Management scorecard KPIs (Top Talent Review, IDPs, PLI).",
            "input_schema": _SUCCESSION_SCHEMA,
        },
        {
            "name": "get_succession_bench",
            "description": "Same succession data as get_succession_coverage, but the attached chart "
            "defaults to the critical-role bench table (focus=bench). Pass focus=weak_gaps or "
            "c_suite when the question is about gaps or C-level only. Prefer this over overview "
            "when listing specific roles.",
            "input_schema": _SUCCESSION_SCHEMA,
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


def _succession_payload(args: dict, *, default_focus: str = "overview") -> dict:
    code = (args.get("company_code") or "").strip().upper() or None
    period = (args.get("period") or "").strip() or None
    focus = loader.normalize_succession_focus(args.get("focus") or default_focus)
    data = loader.succession(code)
    as_of = data.get("as_of")
    freshness = {
        "as_of": as_of,
        "requested_period": period,
        "stale": bool(period and as_of and period != as_of),
        "note": (
            f"Fixture as_of {as_of}; requested {period} — treat as demo snapshot, not live HRIS."
            if period and as_of and period != as_of
            else (f"Fixture as_of {as_of}." if as_of else "Fixture-backed demo snapshot.")
        ),
    }
    out = {
        **data,
        "freshness": freshness,
        "focus": focus,
        "artifact": loader.artifact_for("succession", data, focus=focus),
    }
    return out


def dispatch(name: str, args: dict, db: Session, who: Principal) -> dict:
    del db, who  # fixture-backed; principal reserved for future scoping
    if name == "get_workforce_pulse":
        code = (args.get("company_code") or "").strip().upper() or None
        data = loader.pulse(code)
        return {**data, "artifact": loader.artifact_for("pulse", data)}
    if name == "get_skills_gap":
        data = loader.skills()
        return {**data, "artifact": loader.artifact_for("skills", data)}
    if name == "get_succession_coverage":
        return _succession_payload(args, default_focus="overview")
    if name == "get_succession_bench":
        return _succession_payload(args, default_focus="bench")
    if name == "list_draft_actions":
        data = loader.draft_actions()
        key = (args.get("key") or "").strip()
        drafts = data.get("drafts") or []
        if key:
            drafts = [d for d in drafts if d.get("key") == key]
        out = {"drafts": drafts, "artifact": loader.artifact_for("actions", {"drafts": drafts})}
        return out
    return {"error": f"unknown workforce tool {name}"}
