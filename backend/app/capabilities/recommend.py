"""Recommend which capability might supply each of the 19 sourced KPIs.

Deterministic and explainable: name overlap plus how well the capability's output fields cover the
KPI's raw count fields. It only proposes tools whose arguments the platform can fill automatically
(company and period); an admin reviews every proposal before it is used.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.db.models import Capability, KpiMapping
from app.ingestion.raw import SPECS

MIN_SCORE = 0.35
TOP_PER_KPI = 3
_STOP = {"rate", "of", "the", "for", "in", "to", "and", "within", "timelines", "timeliness", "get", "fetch", "stats",
         "count", "counts", "data", "info"}


def tokens(text: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return {t for t in re.split(r"[^a-z0-9]+", spaced.lower()) if t and t not in _STOP}


def _similar(a: str, b: str) -> bool:
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))


def _overlap(want: set[str], have: set[str]) -> float:
    return 0.0 if not want else sum(any(_similar(w, h) for h in have) for w in want) / len(want)


def output_paths(schema: dict | None, prefix: str = "", depth: int = 0) -> list[str]:
    """Dotted paths to scalar fields in an output schema (two levels deep)."""
    if not schema or depth > 2:
        return []
    paths = []
    for name, sub in (schema.get("properties") or {}).items():
        if not isinstance(sub, dict):
            continue
        path = f"{prefix}{name}"
        if sub.get("type") == "object":
            paths += output_paths(sub, path + ".", depth + 1)
        else:
            paths.append(path)
    return paths


def arg_template(input_schema: dict) -> dict | None:
    """Fill company/period/year/month arguments automatically; None if a required one cannot be filled."""
    tpl: dict[str, str] = {}
    required = set(input_schema.get("required", []))
    for name in (input_schema.get("properties") or {}):
        t = tokens(name) | {name.lower()}
        if t & {"company", "entity", "ic", "org", "organization", "organisation", "companycode"}:
            tpl[name] = "{company_code}"
        elif t & {"period", "ym", "yearmonth", "reporting"}:
            tpl[name] = "{period}"
        elif "year" in t or "fy" in t:
            tpl[name] = "{year}"
        elif "month" in t:
            tpl[name] = "{month}"
        elif name in required:
            return None
    return tpl


def field_map(kpi: str, schema: dict | None) -> tuple[dict, float]:
    paths = output_paths(schema)
    fields = SPECS[kpi].fields
    mapped = {}
    for f in fields:
        want = tokens(f)
        best = max(paths, key=lambda p: _overlap(want, tokens(p.split(".")[-1])), default=None)
        if best and _overlap(want, tokens(best.split(".")[-1])) >= 0.99:
            mapped[f] = best
    return mapped, len(mapped) / len(fields)


def recommend(db: Session, who: Principal) -> list[KpiMapping]:
    caps = [c for c in db.scalars(select(Capability).where(Capability.removed.is_(False),
                                                           Capability.deprecated.is_(False)))
            if c.risk == "read"]
    approved = {m.kpi_key for m in db.scalars(select(KpiMapping).where(KpiMapping.status == "approved"))}
    out: list[KpiMapping] = []
    for kpi in SPECS:
        if kpi in approved:
            continue
        kt = tokens(kpi)
        scored = []
        for cap in caps:
            tpl = arg_template(cap.input_schema)
            if tpl is None:  # cannot be called automatically for a company and period
                continue
            name_score = _overlap(kt, tokens(cap.name) | tokens(cap.description))
            fmap, cover = field_map(kpi, cap.output_schema)
            if cap.output_schema:
                if cover < 0.5:
                    continue
                score = 0.4 * name_score + 0.6 * cover
                reasons = [f"{round(cover * 100)}% of the KPI's fields found in the output ({', '.join(fmap) or 'none'})"]
            else:
                if name_score < 0.6:
                    continue
                score = 0.4 * name_score
                reasons = ["no output schema: the field mapping must be set by hand before approval"]
            if name_score:
                reasons.append(f"name matches {round(name_score * 100)}% of the KPI's terms")
            if score >= MIN_SCORE:
                scored.append((score, cap, fmap, tpl, reasons))
        for score, cap, fmap, tpl, reasons in sorted(scored, key=lambda s: -s[0])[:TOP_PER_KPI]:
            m = db.scalar(select(KpiMapping).where(KpiMapping.kpi_key == kpi, KpiMapping.capability_id == cap.id))
            if m is None:
                m = KpiMapping(kpi_key=kpi, capability_id=cap.id, field_map=fmap, arg_template=tpl,
                               status="recommended", score=round(score, 3), reasons=reasons, created_by="system")
                db.add(m)
            elif m.status == "recommended":  # refresh an open proposal; never touch reviewed ones
                m.score, m.reasons = round(score, 3), reasons
            else:
                continue
            out.append(m)
    db.commit()
    return out
