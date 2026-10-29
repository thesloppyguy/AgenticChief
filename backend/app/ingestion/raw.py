"""Raw source counts -> KPI achievement. The single place these formulas live.

Extractors (live or stub) return raw counts per KPI; this module validates them and applies the
PRD formulas. Keeping raw counts also gives every stored value real lineage (numerator/denominator).
"""
from __future__ import annotations

from dataclasses import dataclass

Raw = dict[str, float | None]


class RawDataError(ValueError):
    """A source returned values that cannot be valid (e.g. 120 joined of 100 offers)."""


@dataclass(frozen=True)
class Metric:
    achievement: float | None  # None = no value (never zero)
    numerator: float | None = None
    denominator: float | None = None


@dataclass(frozen=True)
class Spec:
    kind: str  # "ratio" | "value" | "exits"
    fields: tuple[str, ...]
    bounded: bool = True  # ratio numerator must not exceed denominator


SPECS: dict[str, Spec] = {
    "offer_to_joining": Spec("ratio", ("joined", "offers")),
    "time_to_fill": Spec("value", ("avg_days", "positions_closed")),
    "new_hire_retention_12m": Spec("ratio", ("retained", "cohort")),
    "ppw_on_time": Spec("value", ("value",)),
    "kra_submission": Spec("ratio", ("submitted", "eligible")),
    "mid_term_review": Spec("ratio", ("completed", "eligible")),
    "continuous_feedback": Spec("value", ("avg_entries_per_employee",)),
    "tni_employees": Spec("ratio", ("completed", "eligible")),
    "training_calendar": Spec("value", ("value",)),
    "tni_fulfilment": Spec("ratio", ("fulfilled", "identified")),
    # Level 1 feedback arrives on a 1-5 scale; the target (80) is a percentage, so rating/5*100.
    "l1_feedback": Spec("value", ("avg_rating_5",)),
    "role_skill_coverage": Spec("ratio", ("mapped", "in_scope")),
    "pli_assessment": Spec("ratio", ("completed", "total")),
    "idp_creation_rate": Spec("ratio", ("with_idp", "target_employees")),
    "ahc_completion": Spec("ratio", ("completed", "eligible")),
    "platform_adoption": Spec("ratio", ("unique_logins", "active_employees")),
    "overall_retention": Spec("ratio", ("retentions", "avg_headcount")),
    "top_talent_retention": Spec("exits", ("regrettable_exits", "avg_headcount_cpr7")),
    "trainee_retention": Spec("ratio", ("remaining", "onboarded")),
}


def _get(raw: Raw, name: str) -> float | None:
    v = raw.get(name)
    if v is None:
        return None
    if v < 0:
        raise RawDataError(f"{name} is negative")
    return float(v)


def to_metric(kpi_key: str, raw: Raw) -> Metric:
    spec = SPECS.get(kpi_key)
    if spec is None:
        raise RawDataError(f"{kpi_key} is not a sourced KPI")

    if spec.kind in ("ratio", "exits"):
        num, den = _get(raw, spec.fields[0]), _get(raw, spec.fields[1])
        if num is None or den is None or den == 0:
            return Metric(None, num, den)  # no population -> no value, not zero
        if spec.bounded and num > den:
            raise RawDataError(f"{spec.fields[0]} exceeds {spec.fields[1]}")
        if spec.kind == "exits":
            return Metric(100.0 - num / den * 100, num, den)
        return Metric(num / den * 100, num, den)

    # value kinds
    v = _get(raw, spec.fields[0])
    if v is None:
        return Metric(None)
    if kpi_key == "time_to_fill":
        closed = _get(raw, "positions_closed")
        if closed == 0:
            return Metric(None)  # nothing closed in the period -> no value
    if kpi_key == "l1_feedback":
        if not 1 <= v <= 5:
            raise RawDataError("avg_rating_5 outside 1-5")
        v = v / 5 * 100
    if kpi_key in ("ppw_on_time",) and v not in (0, 1):
        raise RawDataError("ppw_on_time must be 0 or 1")
    if kpi_key == "training_calendar" and v not in (0, 1, 2):
        raise RawDataError("training_calendar must be 0, 1 or 2")
    return Metric(v)
