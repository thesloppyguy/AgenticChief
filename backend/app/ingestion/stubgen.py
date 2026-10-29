"""Synthetic company data: schema, validation, KPI mapping, and a deterministic fallback generator."""
from __future__ import annotations

import hashlib
import random
from typing import Literal

from pydantic import BaseModel

from .raw import SPECS, Raw, RawDataError, to_metric

Archetype = Literal["strong", "steady", "struggling", "early_stage"]


class CompanyRaw(BaseModel):
    """Year-to-date HR counts for one company. Flat so an LLM can fill it reliably."""

    company_code: str
    archetype: Archetype
    headcount: int
    eligible_employees: int
    # Talent acquisition
    offers: int
    joined: int
    avg_days_to_fill: float
    positions_closed: int
    hire_cohort: int
    retained_12m: int
    # Performance management
    ppw_on_time: Literal[0, 1]
    kra_submitted: int
    mid_term_completed: int
    avg_feedback_entries: float
    # Learning & development
    tni_completed: int
    training_calendar: Literal[0, 1, 2]
    tni_identified: int
    tni_fulfilled: int
    avg_rating_5: float
    # Organisational effectiveness / talent management
    skills_mapped: int
    pli_total: int
    pli_completed: int
    idp_target_employees: int
    idps_created: int
    # Engagement / wellness
    ahc_eligible: int
    ahc_completed: int
    unique_logins: int
    # Retention
    retentions: int
    avg_headcount: int
    cpr7_headcount: int
    regrettable_exits: int
    trainees_onboarded: int
    trainees_remaining: int


class CompanyBatch(BaseModel):
    companies: list[CompanyRaw]


def to_kpi_raw(c: CompanyRaw) -> dict[str, Raw]:
    return {
        "offer_to_joining": {"joined": c.joined, "offers": c.offers},
        "time_to_fill": {"avg_days": c.avg_days_to_fill, "positions_closed": c.positions_closed},
        "new_hire_retention_12m": {"retained": c.retained_12m, "cohort": c.hire_cohort},
        "ppw_on_time": {"value": c.ppw_on_time},
        "kra_submission": {"submitted": c.kra_submitted, "eligible": c.eligible_employees},
        "mid_term_review": {"completed": c.mid_term_completed, "eligible": c.eligible_employees},
        "continuous_feedback": {"avg_entries_per_employee": c.avg_feedback_entries},
        "tni_employees": {"completed": c.tni_completed, "eligible": c.eligible_employees},
        "training_calendar": {"value": c.training_calendar},
        "tni_fulfilment": {"fulfilled": c.tni_fulfilled, "identified": c.tni_identified},
        "l1_feedback": {"avg_rating_5": c.avg_rating_5},
        "role_skill_coverage": {"mapped": c.skills_mapped, "in_scope": c.headcount},
        "pli_assessment": {"completed": c.pli_completed, "total": c.pli_total},
        "idp_creation_rate": {"with_idp": c.idps_created, "target_employees": c.idp_target_employees},
        "ahc_completion": {"completed": c.ahc_completed, "eligible": c.ahc_eligible},
        "platform_adoption": {"unique_logins": c.unique_logins, "active_employees": c.headcount},
        "overall_retention": {"retentions": c.retentions, "avg_headcount": c.avg_headcount},
        "top_talent_retention": {"regrettable_exits": c.regrettable_exits,
                                 "avg_headcount_cpr7": c.cpr7_headcount},
        "trainee_retention": {"remaining": c.trainees_remaining, "onboarded": c.trainees_onboarded},
    }


def validate(c: CompanyRaw) -> list[str]:
    """Problems that make a generated company unusable. Reuses the production formulas."""
    problems: list[str] = []
    if c.headcount < 1:
        problems.append("headcount < 1")
    if c.eligible_employees > c.headcount:
        problems.append("eligible_employees > headcount")
    if not 5 <= c.avg_days_to_fill <= 365 and c.positions_closed > 0:
        problems.append("avg_days_to_fill implausible")
    if not 0 <= c.avg_feedback_entries <= 12:
        problems.append("avg_feedback_entries implausible")
    kpi_raw = to_kpi_raw(c)
    assert set(kpi_raw) == set(SPECS)  # every sourced KPI is covered
    for key, raw in kpi_raw.items():
        try:
            to_metric(key, raw)
        except RawDataError as e:
            problems.append(f"{key}: {e}")
    return problems


# --- deterministic fallback -------------------------------------------------------------------

_QUALITY = {"strong": 0.95, "steady": 0.85, "struggling": 0.65, "early_stage": 0.55}
_QUOTA: list[tuple[Archetype, float]] = [("strong", 0.25), ("steady", 0.45), ("struggling", 0.20),
                                         ("early_stage", 0.10)]


def assign_archetype(index: int, total: int) -> Archetype:
    """Spread archetypes across the group deterministically by position (25/45/20/10)."""
    pos = (index * 0.618033988749895) % 1.0  # low-discrepancy, so neighbours differ
    acc = 0.0
    for name, share in _QUOTA:
        acc += share
        if pos < acc:
            return name
    return "steady"


def _rng(*parts: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:8], "big"))


def synthetic_company(code: str, archetype: Archetype | None = None) -> CompanyRaw:
    r = _rng("company", code)
    arch = archetype or r.choice(["strong", "steady", "steady", "struggling", "early_stage"])
    q = _QUALITY[arch]

    def frac(centre: float = q, spread: float = 0.07) -> float:
        return min(1.0, max(0.05, r.gauss(centre, spread)))

    headcount = int(min(4000, max(60, r.lognormvariate(5.8, 0.8))))
    eligible = max(1, int(headcount * r.uniform(0.85, 0.98)))
    offers = max(5, int(headcount * r.uniform(0.08, 0.3)))
    joined = min(offers, round(offers * frac(q + 0.03)))
    cohort = max(1, joined + r.randint(0, 5))
    pli_total = max(1, int(headcount * r.uniform(0.05, 0.15)))
    target = max(1, int(headcount * r.uniform(0.1, 0.3)))
    ahc_elig = max(1, int(headcount * r.uniform(0.7, 0.95)))
    trainees = r.randint(0, max(1, headcount // 40))
    cpr7 = max(1, int(headcount * r.uniform(0.06, 0.15)))
    tni_ident = max(1, int(headcount * r.uniform(0.8, 3.0)))
    return CompanyRaw(
        company_code=code, archetype=arch, headcount=headcount, eligible_employees=eligible,
        offers=offers, joined=joined,
        avg_days_to_fill=round(r.gauss(60 / max(q, 0.3) * 0.95, 8), 1),
        positions_closed=max(1, int(offers * r.uniform(0.6, 1.0))),
        hire_cohort=cohort, retained_12m=min(cohort, round(cohort * frac(q + 0.05))),
        ppw_on_time=1 if r.random() < q else 0,
        kra_submitted=round(eligible * frac()), mid_term_completed=round(eligible * frac(q - 0.05)),
        avg_feedback_entries=round(max(0.0, r.gauss(2.4 * q + 0.2, 0.35)), 2),
        tni_completed=round(eligible * frac()), training_calendar=2 if r.random() < q else r.choice([0, 1]),
        tni_identified=tni_ident, tni_fulfilled=min(tni_ident, round(tni_ident * frac(q - 0.1))),
        avg_rating_5=round(min(5.0, max(1.0, r.gauss(3.0 + 1.5 * q, 0.25))), 2),
        skills_mapped=round(headcount * frac(q - 0.05, 0.1)),
        pli_total=pli_total, pli_completed=round(pli_total * frac()),
        idp_target_employees=target, idps_created=round(target * frac(q - 0.05)),
        ahc_eligible=ahc_elig, ahc_completed=round(ahc_elig * frac(q - 0.1, 0.1)),
        unique_logins=round(headcount * frac(q - 0.1, 0.1)),
        retentions=round(headcount * min(1.0, frac(0.9 + 0.08 * q, 0.03))),
        avg_headcount=headcount, cpr7_headcount=cpr7,
        regrettable_exits=min(cpr7, round(cpr7 * max(0.0, r.gauss(0.2 * (1.2 - q), 0.03)))),
        trainees_onboarded=trainees, trainees_remaining=min(trainees, round(trainees * frac(q - 0.05, 0.1))),
    )
