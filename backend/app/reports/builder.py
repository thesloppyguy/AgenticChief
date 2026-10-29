"""Build the monthly review document from computed scorecards. Pure: no database, no LLM.

Every number in the report comes from the scoring service's output; this only arranges and compares it.
"""
from __future__ import annotations

from collections import Counter

from app.kpi_registry.seed import DEFAULT_CONFIG
from app.scoring import status_for

TOP_N = 5
RED_LIST_MAX = 15
SAMPLE_CODES = 10


def _status(score: float | None) -> str | None:
    s = status_for(score, DEFAULT_CONFIG)
    return s.value if s else None


def _delta(now: float | None, before: float | None) -> float | None:
    return None if now is None or before is None else round(now - before, 1) + 0.0  # +0.0 turns -0.0 into 0.0


def _r(x: float | None, n: int = 1) -> float | None:
    return None if x is None else round(x, n)


def _distribution(companies: list[dict]) -> dict[str, int]:
    c = Counter(co["status"] or "none" for co in companies)
    return {k: c.get(k, 0) for k in ("green", "amber", "red", "none")}


def _weakest(pillars: list[dict], n: int = 2) -> list[dict]:
    scored = [p for p in pillars if p["score"] is not None]
    return [{"pillar": p["pillar"], "score": _r(p["score"])} for p in sorted(scored, key=lambda p: p["score"])[:n]]


def build_report(period: str, prev_period: str | None, card: dict, prev: dict | None,
                 lineage: dict, generated_by: str, generated_at: str) -> dict:
    g = card["group"]
    pg = prev["group"] if prev else None
    prev_pillars = {p["pillar"]: p for p in pg["pillars"]} if pg else {}

    pillars = []
    for p in g["pillars"]:
        before = prev_pillars.get(p["pillar"])
        pillars.append({
            "pillar": p["pillar"], "score": _r(p["score"]), "status": _status(p["score"]),
            "previous": _r(before["score"]) if before else None,
            "delta": _delta(p["score"], before["score"] if before else None),
            "eligible_weight": _r(p["eligible_weight"], 2),
        })

    prev_cos = {c["code"]: c for c in prev["companies"]} if prev else {}
    movers = []
    for c in card["companies"]:
        b = prev_cos.get(c["code"])
        d = _delta(c["score"], b["score"] if b else None)
        if d is not None:
            movers.append({"code": c["code"], "score": _r(c["score"]), "previous": _r(b["score"]), "delta": d})
    improved = sorted((m for m in movers if m["delta"] > 0), key=lambda m: -m["delta"])[:TOP_N]
    declined = sorted((m for m in movers if m["delta"] < 0), key=lambda m: m["delta"])[:TOP_N]

    reds = sorted((c for c in card["companies"] if c["status"] == "red"), key=lambda c: c["score"])
    newly_red = [c["code"] for c in reds if prev_cos.get(c["code"]) and prev_cos[c["code"]]["status"] != "red"]

    # Exceptions: why numbers are missing, split by cause (a connection gap is not a company's failure).
    missing: dict[str, list[str]] = {}
    for c in card["companies"]:
        for p in c["pillars"]:
            for k in p["kpis"]:
                if k["excluded_reason"] == "missing":
                    missing.setdefault(k["key"], []).append(c["code"])
    group_kpis = [k for p in g["pillars"] for k in p["kpis"]]
    low_cov = [c["code"] for c in card["companies"] if c["pillar_coverage"] < 1]
    problem_sources = [s for s in lineage["sources"] if s["last_run"] and s["last_run"]["status"] != "success"]

    caveats: list[str] = []
    if card["synthetic_data"]:
        caveats.append("This report contains synthetic (stub or seed) data and must not be used for decisions.")
    if card["no_source_kpis"]:
        caveats.append(f"{len(card['no_source_kpis'])} KPIs have no data source and are excluded from every score.")
    if g["pillar_coverage"] < 1:
        caveats.append(f"The Group score rests on {round(g['pillar_coverage'] * 100)}% of the scorecard weight.")
    if g["companies_with_data"] < g["companies_in_scope"]:
        caveats.append(f"Only {g['companies_with_data']} of {g['companies_in_scope']} companies have any data.")
    if prev is None:
        caveats.append("No month-over-month comparison: this is the first month of the fiscal year.")
    if problem_sources:
        caveats.append("Some sources had failed or partial ingestion runs: "
                       + ", ".join(s["label"] for s in problem_sources) + ".")

    return {
        "meta": {"period": period, "previous_period": prev_period, "calc_version": card["calc_version"],
                 "generated_at": generated_at, "generated_by": generated_by, "scope": card["scope"],
                 "synthetic_data": card["synthetic_data"], "companies_in_scope": g["companies_in_scope"],
                 "companies_with_data": g["companies_with_data"]},
        "headline": {
            "group_score": _r(g["score"]), "group_status": g["status"],
            "previous_group_score": _r(pg["score"]) if pg else None,
            "delta": _delta(g["score"], pg["score"] if pg else None),
            "coverage_pct": round(g["pillar_coverage"] * 100),
            "pillars": pillars,
            "distribution": _distribution(card["companies"]),
            "previous_distribution": _distribution(prev["companies"]) if prev else None,
        },
        "movers": {"improved": improved, "declined": declined},
        "attention": {
            "red_count": len(reds), "newly_red": newly_red,
            "red": [{"code": c["code"], "score": _r(c["score"]), "weakest_pillars": _weakest(c["pillars"])}
                    for c in reds[:RED_LIST_MAX]],
        },
        "exceptions": {
            "missing": sorted(({"kpi": k, "missing_count": len(v), "sample": v[:SAMPLE_CODES]}
                               for k, v in missing.items()), key=lambda e: -e["missing_count"]),
            "no_source": list(card["no_source_kpis"]),
            "not_due": sorted(k["key"] for k in group_kpis if k["excluded_reason"] == "not_due"),
            "low_coverage": {"count": len(low_cov), "sample": low_cov[:30]},
            "ingestion_problems": [{"source": s["source"], "status": s["last_run"]["status"],
                                    "failed": s["last_run"]["companies_failed"]} for s in problem_sources],
        },
        "lineage": lineage,
        "caveats": caveats,
    }
