"""Load deterministic workforce YAML from backend/seed/lnt_group/workforce/."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.fixtures.paths import GROUP_DIR

WORKFORCE_DIR = GROUP_DIR / "workforce"
SECTIONS = ("pulse", "skills", "succession", "actions")

SUCCESSION_FOCUSES = frozenset({"overview", "weak_gaps", "c_suite", "bench"})
_WEAK_READINESS = frozenset({"no_ready", "ready_1_2y"})
_WEAK_STATUS = frozenset({"thin", "no_ready_internal", "gap"})
_C_SUITE_RE = re.compile(
    r"(?i)\b(CHRO|CEO|CFO|CTO|CMO|COO|CPO|CIO|CXO|Chief\s+\w+|C-[A-Z]{2,})\b"
)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


@lru_cache(maxsize=8)
def load_section(name: str) -> dict[str, Any]:
    key = name.strip().lower()
    if key not in SECTIONS:
        raise ValueError(f"unknown workforce section '{name}'")
    return dict(_read_yaml(WORKFORCE_DIR / f"{key}.yaml"))


def clear_cache() -> None:
    load_section.cache_clear()


def pulse(company_code: str | None = None) -> dict[str, Any]:
    """Group workforce pulse fixture, optionally narrowed to one IC.

    Per-IC slices live under ``by_ic.<CODE>``. Unknown codes return an honest
    empty payload rather than silently falling back to Group totals.
    """
    data = load_section("pulse")
    code = (company_code or "").strip().upper()
    if not code:
        return data

    by_ic = data.get("by_ic") or {}
    slice_ = by_ic.get(code)
    if not isinstance(slice_, dict):
        return {
            "as_of": data.get("as_of"),
            "company_code": code,
            "scope": "ic",
            "available": False,
            "missing": [
                "narrative",
                "insights",
                "cells",
                "top_issues",
                "scorecard_exception",
            ],
            "narrative": "",
            "insights": [
                f"No workforce pulse fixture for IC '{code}'. "
                "Do not invent IC pulse numbers."
            ],
            "cells": [],
            "top_issues": [],
            "scorecard_exception": None,
        }

    return {
        "as_of": data.get("as_of"),
        "company_code": code,
        "scope": "ic",
        "available": True,
        "name": slice_.get("name"),
        "aliases": slice_.get("aliases") or [],
        "narrative": slice_.get("narrative") or "",
        "synthesized_by": data.get("synthesized_by"),
        "insights": slice_.get("insights") or [],
        "cells": slice_.get("cells") or [],
        "top_issues": slice_.get("top_issues") or [],
        "scorecard_exception": slice_.get("scorecard_exception"),
    }


def skills() -> dict[str, Any]:
    return load_section("skills")


def succession(company_code: str | None = None) -> dict[str, Any]:
    """Group succession fixture, optionally narrowed to one IC.

    Per-IC slices live under ``by_ic.<CODE>``. Bench rows are filtered by
    ``company_code`` when present. Unknown codes return an honest empty payload
    rather than silently falling back to Group totals.
    """
    data = load_section("succession")
    code = (company_code or "").strip().upper()
    if not code:
        return data

    by_ic = data.get("by_ic") or {}
    slice_ = by_ic.get(code)
    if not isinstance(slice_, dict):
        return {
            "as_of": data.get("as_of"),
            "company_code": code,
            "scope": "ic",
            "available": False,
            "missing": [
                "critical_roles",
                "successor_nominations",
                "readiness",
                "nine_box",
                "incumbent_flight_risk",
            ],
            "headline": {},
            "insights": [
                f"No succession coverage fixture for IC '{code}'. "
                "Do not substitute Talent Management scorecard KPIs."
            ],
            "by_function": [],
            "bench": [],
        }

    bench = [
        b for b in (data.get("bench") or [])
        if str(b.get("company_code") or "").upper() == code
    ]
    return {
        "as_of": data.get("as_of"),
        "company_code": code,
        "scope": "ic",
        "available": True,
        "name": slice_.get("name"),
        "aliases": slice_.get("aliases") or [],
        "headline": slice_.get("headline") or {},
        "insights": slice_.get("insights") or [],
        "by_function": slice_.get("by_function") or [],
        "bench": bench,
        "subtitle": slice_.get("subtitle")
        or f"Succession coverage for {slice_.get('name') or code}.",
    }


def draft_actions() -> dict[str, Any]:
    return load_section("actions")


def normalize_succession_focus(focus: str | None) -> str:
    key = (focus or "overview").strip().lower().replace("-", "_")
    aliases = {
        "weak": "weak_gaps",
        "gaps": "weak_gaps",
        "weak_or_no": "weak_gaps",
        "no_successor": "weak_gaps",
        "clevel": "c_suite",
        "c_level": "c_suite",
        "csuite": "c_suite",
        "executive": "c_suite",
        "roles": "bench",
        "critical_roles": "bench",
    }
    key = aliases.get(key, key)
    return key if key in SUCCESSION_FOCUSES else "overview"


def _is_weak_bench(row: dict[str, Any]) -> bool:
    readiness = str(row.get("readiness") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    return readiness in _WEAK_READINESS or status in _WEAK_STATUS


def _is_c_suite_bench(row: dict[str, Any]) -> bool:
    return bool(_C_SUITE_RE.search(str(row.get("role") or "")))


def _bench_item(b: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": b.get("role"),
        "business": b.get("business"),
        "company_code": b.get("company_code"),
        "ready_pct": b.get("ready_pct"),
        "readiness": b.get("readiness"),
        "status": b.get("status"),
        "nine_box": b.get("nine_box"),
        "incumbent_flight_risk": b.get("incumbent_flight_risk"),
        "vacancy_exposure": b.get("vacancy_exposure"),
        "successor": b.get("successor"),
        "development_move": b.get("development_move"),
        "note": b.get("note"),
    }


def _function_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "function": r.get("function"),
            "ready_now": r.get("ready_now"),
            "ready_1_2y": r.get("ready_1_2y"),
            "no_successor": r.get("no_successor"),
            "is_new": "new" in str(r.get("function") or "").lower(),
        }
        for r in rows
    ]


def _scope_label(payload: dict[str, Any]) -> str:
    if (payload.get("scope") or "group") == "ic":
        return str(payload.get("name") or payload.get("company_code") or "IC")
    return "Group"


def _overview_headline(headline: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "label": "Critical roles tracked",
            "value": headline.get("critical_roles_tracked"),
            "note": "leadership & technical",
        },
        {
            "label": "Ready-now coverage",
            "value": headline.get("ready_now_coverage_pct"),
            "unit": "%",
            "delta_pct": headline.get("ready_now_delta_pts"),
            "delta_direction": "down"
            if (headline.get("ready_now_delta_pts") or 0) < 0
            else "flat",
            "note": "vs last year",
            "tone": "alert",
        },
        {
            "label": "Weak / no successor",
            "value": headline.get("weak_or_no_successor"),
            "note": "new businesses lead",
            "tone": "alert",
        },
        {
            "label": "Internal fill rate",
            "value": headline.get("internal_fill_rate_pct"),
            "unit": "%",
            "note": f"target {headline.get('internal_fill_target_pct', 60)}%",
            "tone": "alert",
        },
    ]


def _bench_headline(bench: list[dict[str, Any]]) -> list[dict[str, Any]]:
    no_ready = sum(
        1 for b in bench if str(b.get("readiness") or "").lower() == "no_ready"
    )
    thin = sum(
        1 for b in bench if str(b.get("readiness") or "").lower() == "ready_1_2y"
    )
    high_flight = sum(
        1
        for b in bench
        if str(b.get("incumbent_flight_risk") or "").lower() == "high"
    )
    return [
        {
            "label": "Roles in view",
            "value": len(bench),
            "note": "from succession fixture",
        },
        {
            "label": "No ready successor",
            "value": no_ready,
            "tone": "alert" if no_ready else "good",
        },
        {
            "label": "Ready in 1–2 years",
            "value": thin,
            "tone": "alert" if thin else None,
        },
        {
            "label": "High flight risk",
            "value": high_flight,
            "tone": "alert" if high_flight else "good",
        },
    ]


def _succession_artifact(
    payload: dict[str, Any],
    *,
    focus: str = "overview",
) -> dict[str, Any]:
    """Build a chat chart for succession — shape depends on ``focus``."""
    focus = normalize_succession_focus(focus)
    scope = _scope_label(payload)
    all_bench = list(payload.get("bench") or [])
    all_functions = list(payload.get("by_function") or [])
    headline = payload.get("headline") or {}
    default_insights = [
        _clean(i) for i in (payload.get("insights") or []) if _clean(i)
    ]

    if focus == "weak_gaps":
        bench = [b for b in all_bench if _is_weak_bench(b)]
        functions = [
            r for r in all_functions if int(r.get("no_successor") or 0) > 0
        ]
        title = f"Weak / no successor · {scope}"
        subtitle = (
            f"{len(bench)} critical roles with thin or empty benches"
            if bench
            else f"No weak-bench roles in the {scope} succession fixture."
        )
        insights = [
            f"{len(bench)} of {len(all_bench) or headline.get('critical_roles_tracked') or '—'} "
            f"listed critical roles are weak or have no ready successor.",
            *default_insights[:2],
        ]
        return {
            "kind": "succession_stack",
            "title": title,
            "subtitle": subtitle,
            "source": "workforce.succession",
            "export_key": "workforce_succession",
            "schedule_key": "workforce_brief",
            "focus": focus,
            "insights": [_clean(i) for i in insights if _clean(i)],
            "headline": _bench_headline(bench),
            "functions": _function_items(functions),
            "bench": [_bench_item(b) for b in bench],
            "company_code": payload.get("company_code"),
            "scope": payload.get("scope") or "group",
            "as_of": payload.get("as_of"),
            "available": payload.get("available", True),
            "missing": payload.get("missing") or [],
        }

    if focus == "c_suite":
        bench = [b for b in all_bench if _is_c_suite_bench(b)]
        title = f"C-suite succession · {scope}"
        subtitle = (
            f"{len(bench)} C-level role(s) in the succession fixture"
            if bench
            else f"No C-suite roles listed in the {scope} succession fixture."
        )
        insights = [
            (
                f"{sum(1 for b in bench if _is_weak_bench(b))} of {len(bench)} "
                "C-suite roles are weak or thin."
                if bench
                else "C-suite bench rows are empty for this scope."
            ),
            *default_insights[:1],
        ]
        return {
            "kind": "succession_stack",
            "title": title,
            "subtitle": subtitle,
            "source": "workforce.succession",
            "export_key": "workforce_succession",
            "schedule_key": "workforce_brief",
            "focus": focus,
            "insights": [_clean(i) for i in insights if _clean(i)],
            "headline": _bench_headline(bench),
            "functions": [],
            "bench": [_bench_item(b) for b in bench],
            "company_code": payload.get("company_code"),
            "scope": payload.get("scope") or "group",
            "as_of": payload.get("as_of"),
            "available": payload.get("available", True),
            "missing": payload.get("missing") or [],
        }

    if focus == "bench":
        title = f"Succession bench · {scope}"
        subtitle = (
            _clean(payload.get("subtitle"))
            or f"Critical-role successors for {scope}."
        )
        return {
            "kind": "succession_stack",
            "title": title,
            "subtitle": subtitle,
            "source": "workforce.succession",
            "export_key": "workforce_succession",
            "schedule_key": "workforce_brief",
            "focus": focus,
            "insights": default_insights,
            "headline": _bench_headline(all_bench) if all_bench else _overview_headline(headline),
            "functions": [],
            "bench": [_bench_item(b) for b in all_bench],
            "company_code": payload.get("company_code"),
            "scope": payload.get("scope") or "group",
            "as_of": payload.get("as_of"),
            "available": payload.get("available", True),
            "missing": payload.get("missing") or [],
        }

    # overview — full coverage dashboard
    title = (
        f"Succession coverage by function · {scope}"
        if (payload.get("scope") or "group") == "ic"
        else "Succession coverage by function"
    )
    return {
        "kind": "succession_stack",
        "title": title,
        "subtitle": _clean(
            payload.get("subtitle")
            or "Green energy and semiconductors — the growth engines — have the thinnest ready-now benches."
        ),
        "source": "workforce.succession",
        "export_key": "workforce_succession",
        "schedule_key": "workforce_brief",
        "focus": "overview",
        "insights": default_insights,
        "headline": _overview_headline(headline),
        "functions": _function_items(all_functions),
        "bench": [_bench_item(b) for b in all_bench],
        "company_code": payload.get("company_code"),
        "scope": payload.get("scope") or "group",
        "as_of": payload.get("as_of"),
        "available": payload.get("available", True),
        "missing": payload.get("missing") or [],
    }


def artifact_for(
    section: str,
    payload: dict[str, Any],
    *,
    focus: str | None = None,
) -> dict[str, Any] | None:
    """Structured chart payload for chat SSE (dashboard-style widgets)."""
    if section == "pulse":
        cells = payload.get("cells") or []
        issues = payload.get("top_issues") or []
        exception = payload.get("scorecard_exception") or {}
        scope = payload.get("scope") or "group"
        ic_name = payload.get("name")
        company_code = payload.get("company_code")
        if scope == "ic":
            subtitle = f"{ic_name or company_code or 'IC'} people signals for this briefing window."
        else:
            subtitle = "Group people signals for this briefing window."
        return {
            "kind": "workforce_pulse",
            "title": "Workforce pulse",
            "subtitle": subtitle,
            "source": "workforce.pulse",
            "export_key": "workforce_pulse",
            "schedule_key": "workforce_brief",
            "scope": scope,
            "company_code": company_code,
            "available": payload.get("available", True),
            "narrative": _clean(payload.get("narrative")),
            "insights": [_clean(i) for i in (payload.get("insights") or []) if _clean(i)],
            "items": [
                {
                    "label": c.get("label") or c.get("key"),
                    "value": c.get("value"),
                    "unit": c.get("unit") or "",
                    "delta_pct": c.get("delta_pct"),
                    "delta_direction": c.get("delta_direction"),
                    "note": c.get("note"),
                    "tone": c.get("tone"),
                }
                for c in cells
            ],
            "issues": [
                {
                    "rank": i.get("rank"),
                    "title": i.get("title"),
                    "summary": _clean(i.get("summary")),
                    "severity": i.get("severity"),
                    "priority_label": i.get("priority_label"),
                    "tags": i.get("tags") or [],
                    "flagged_by": i.get("flagged_by") or [],
                    "recommendation": _clean(i.get("recommendation")),
                    "company_code": i.get("company_code"),
                    "company_codes": i.get("company_codes") or [],
                    "action_key": i.get("action_key"),
                }
                for i in issues
            ],
            "exceptions": (
                [
                    {
                        "title": exception.get("title") or exception.get("pillar"),
                        "score": exception.get("score"),
                        "status": exception.get("status") or "red",
                        "detail": _clean(exception.get("detail")),
                        "action_key": exception.get("action_key"),
                        "company_code": exception.get("company_code"),
                        "company_codes": exception.get("company_codes") or [],
                    }
                ]
                if exception
                else []
            ),
        }
    if section == "skills":
        domains = payload.get("domains") or []
        headline = payload.get("headline") or {}
        bvb = payload.get("build_vs_buy") or {}
        return {
            "kind": "skills_demand_supply",
            "title": "Skill demand vs available supply",
            "subtitle": _clean(
                payload.get("subtitle")
                or "Future-critical roles · next 24 months."
            ),
            "source": "workforce.skills",
            "export_key": "workforce_skills",
            "schedule_key": "workforce_brief",
            "insights": [_clean(i) for i in (payload.get("insights") or []) if _clean(i)],
            "headline": [
                {
                    "label": "Future-critical roles · 24mo",
                    "value": headline.get("future_critical_roles_24mo"),
                    "note": "green H₂, semi, power, digital",
                },
                {
                    "label": "Projected supply",
                    "value": headline.get("projected_supply"),
                    "note": "external + internal-ready",
                    "tone": "alert",
                },
                {
                    "label": "Capability gap",
                    "value": headline.get("capability_gap"),
                    "note": "roles unmet",
                    "tone": "alert",
                },
                {
                    "label": "Buildable internally",
                    "value": headline.get("buildable_internally_pct"),
                    "unit": "%",
                    "note": "with a capability programme",
                    "tone": "good",
                },
            ],
            "domains": [
                {
                    "label": d.get("label"),
                    "demand": d.get("demand"),
                    "supply": d.get("supply"),
                    "gap": d.get("gap"),
                    "path": d.get("path"),
                    "insight": _clean(d.get("insight")),
                }
                for d in domains
            ],
            "build_vs_buy": {
                "focus": bvb.get("focus"),
                "insight": _clean(bvb.get("insight")),
                "metrics": bvb.get("metrics") or [],
            }
            if bvb
            else None,
            "capacity_insight": _clean(payload.get("capacity_insight")),
            "mobility_insight": _clean(payload.get("mobility_insight")),
            "mobility": payload.get("mobility_adjacency") or [],
            "capacity": payload.get("internal_build_capacity") or [],
        }
    if section == "succession":
        return _succession_artifact(payload, focus=normalize_succession_focus(focus))
    if section == "actions":
        drafts = payload.get("drafts") or []
        return {
            "kind": "action_drafts",
            "title": "Ready for your decision",
            "subtitle": "Recommended actions with approval & execution attached.",
            "source": "workforce.actions",
            "export_key": "workforce_actions",
            "schedule_key": None,
            "drafts": [
                {
                    "key": d.get("key"),
                    "title": d.get("title"),
                    "summary": _clean(d.get("summary")),
                    "detail": _clean(d.get("detail")),
                    "severity": d.get("severity"),
                    "sla": d.get("sla"),
                    "sla_style": d.get("sla_style") or "pill",
                    "action": d.get("action"),
                    "propose_args": d.get("propose_args") or {},
                    "roi": d.get("roi"),
                    "drivers": d.get("drivers") or [],
                    "channels": d.get("channels") or [],
                    "routes_to": d.get("routes_to") or [],
                    "insights": [_clean(i) for i in (d.get("insights") or []) if _clean(i)],
                }
                for d in drafts
            ],
        }
    return None
