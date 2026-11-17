"""Synthetic company data: schema, validation, KPI mapping, and a deterministic fallback generator."""
from __future__ import annotations

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


def synthetic_company(code: str, archetype: Archetype | None = None) -> CompanyRaw:
    """Derive CompanyRaw from a simulated employee census (single source of truth)."""
    from app.workforce.employee_sim.aggregate import to_company_raw
    from app.workforce.employee_sim.generate import simulate_ic

    return to_company_raw(simulate_ic(code, archetype))
