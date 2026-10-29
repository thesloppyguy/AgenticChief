"""April-March fiscal calendar helpers."""
from __future__ import annotations

from .models import KpiDef


def fiscal_index(month: int) -> int:
    """April=0 ... March=11."""
    return (month - 4) % 12


def is_due(kpi: KpiDef, month: int) -> bool:
    if kpi.due_from_month is None:
        return True
    return fiscal_index(month) >= fiscal_index(kpi.due_from_month)


def target_for(kpi: KpiDef, month: int, prorate: bool = False) -> float:
    """Latest step whose start month has been reached in the fiscal year; optionally pro-rated for
    year-to-date KPIs (target x months elapsed / 12)."""
    target = kpi.target
    if prorate and kpi.cumulative:
        return target * (fiscal_index(month) + 1) / 12
    for from_month, step_target in sorted(kpi.target_steps, key=lambda s: fiscal_index(s[0])):
        if fiscal_index(month) >= fiscal_index(from_month):
            target = step_target
    return target
