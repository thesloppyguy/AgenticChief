"""Seed values for the 4 manual KPIs (they have no source system), for dev, demos and load testing.

Rows are tagged source="seed" so the scorecard flags them as synthetic. An editor's real entry
(source="manual") always wins: seeding never overwrites it, and saving through the manual-input page
replaces a seeded value and turns it into a real one.
"""
from __future__ import annotations

import calendar
import hashlib
import random
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, KpiRecord
from app.scoring.fiscal import fiscal_index
from app.services.manual_inputs import ManualInput

from .stubgen import CompanyRaw, synthetic_company

SEED_SOURCE = "seed"
SYNTHETIC_SOURCES = {"demo", SEED_SOURCE}

_QUALITY = {"strong": 0.95, "steady": 0.85, "struggling": 0.65, "early_stage": 0.55}
# Mean GPTW Trust Index by archetype (target is 80).
_GPTW = {"strong": 86, "steady": 77, "struggling": 63, "early_stage": 69}


def _rng(*parts: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:8], "big"))


def _period_end(period: str) -> date:
    y, m = map(int, period.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1])


def _fy_start_year(period: str) -> int:
    y, m = map(int, period.split("-"))
    return y if m >= 4 else y - 1


def manual_inputs(c: CompanyRaw, period: str) -> list[ManualInput]:
    """The four manual KPIs for one company and month. Deterministic, validated by ManualInput."""
    q = _QUALITY[c.archetype]
    fy = _fy_start_year(period)
    month_idx = fiscal_index(int(period.split("-")[1]))  # April = 0
    common = {"company_id": 0, "period": period}  # company_id is filled in by the caller

    # Cost per hire: this month's recruitment spend and hires. Worse companies spend more per hire.
    r = _rng("cph", c.company_code, period)
    hires = max(0, round(c.headcount * r.uniform(0.004, 0.02)))
    per_hire = 60000 * r.uniform(0.7, 1.0) / q * r.uniform(0.9, 1.15)
    cost = round(per_hire * hires)
    cph = ManualInput(**common, kpi_key="cost_per_hire", recruitment_cost=cost, hires=hires)

    # Top talent review: each company holds it in one month (Aug-Dec), or not at all yet.
    # Cumulative: from the month it was held, every later period reports Yes with that date.
    rc = _rng("ttr", c.company_code, str(fy))
    held = rc.random() < q + 0.15
    review_month = rc.randint(8, 12)
    review_date = date(fy if review_month >= 4 else fy + 1, review_month, rc.randint(5, 25))
    reviewed = held and review_date <= _period_end(period)
    ttr = ManualInput(**common, kpi_key="top_talent_review", reviewed=reviewed,
                      review_date=review_date if reviewed else None)

    # IDPs for top talent: year-to-date count, never decreasing, heading to ~target (25) by March.
    final = max(1, round(25 * q * _rng("idp", c.company_code, str(fy)).uniform(0.8, 1.2)))
    ytd = round(final * (month_idx + 1) / 12)
    idp = ManualInput(**common, kpi_key="idps_top_talent", value=float(ytd))

    # GPTW Trust Index: one annual survey result, carried across the year's months.
    # (Open question in the PRD: annual carried forward vs re-entered monthly.)
    score = round(_rng("gptw", c.company_code, str(fy)).gauss(_GPTW[c.archetype], 3), 1)
    gptw = ManualInput(**common, kpi_key="gptw_score", value=max(0.0, min(100.0, score)))
    return [cph, ttr, idp, gptw]


def seed_manual(db: Session, period: str, companies_raw: dict[str, CompanyRaw] | None = None) -> int:
    """Upsert seeded manual KPIs for every active company. Returns rows written."""
    companies_raw = companies_raw or {}
    existing = {(r.company_id, r.kpi_key): r for r in db.scalars(select(KpiRecord).where(
        KpiRecord.period == period,
        KpiRecord.kpi_key.in_(["cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"])))}
    written = 0
    for company in db.scalars(select(Company).where(Company.active).order_by(Company.code)):
        raw = companies_raw.get(company.code) or synthetic_company(company.code)
        for inp in manual_inputs(raw, period):
            rec = existing.get((company.id, inp.kpi_key))
            if rec is not None and rec.source == "manual":
                continue  # a person entered this; never overwrite
            if rec is None:
                rec = KpiRecord(company_id=company.id, kpi_key=inp.kpi_key, period=period, source=SEED_SOURCE)
                db.add(rec)
            rec.source = SEED_SOURCE
            rec.numerator = rec.denominator = rec.detail = None
            if inp.kpi_key == "cost_per_hire":
                rec.numerator, rec.denominator = inp.recruitment_cost, float(inp.hires)  # type: ignore[arg-type]
                rec.achievement = rec.numerator / rec.denominator if rec.denominator else None
            elif inp.kpi_key == "top_talent_review":
                rec.achievement = 1.0 if inp.reviewed else 0.0
                rec.detail = {"reviewed": inp.reviewed,
                              "review_date": inp.review_date.isoformat() if inp.review_date else None}
            else:
                rec.achievement = inp.value
            written += 1
    db.commit()
    return written
