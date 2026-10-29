from __future__ import annotations

from .fiscal import is_due, target_for
from .models import Direction, KpiDef, KpiResult, KpiValue, ScoringConfig


def score_value(
    achievement: float, target: float, direction: Direction, cfg: ScoringConfig
) -> float:
    if direction is Direction.HIGHER:
        score = achievement / target * 100
    elif achievement == 0:
        score = cfg.zero_lower_is_better_score
    else:
        score = target / achievement * 100
    return min(score, cfg.score_cap) if cfg.score_cap is not None else score


def score_kpi(kpi: KpiDef, value: KpiValue | None, month: int, cfg: ScoringConfig) -> KpiResult:
    if not is_due(kpi, month):
        return KpiResult(kpi.key, None, "not_due")
    if kpi.key in cfg.no_source:  # nothing can supply it, so any stored value is stale
        return KpiResult(kpi.key, None, "no_source")
    if value is None or value.achievement is None:
        return KpiResult(kpi.key, None, "missing")
    return KpiResult(
        kpi.key,
        score_value(value.achievement, target_for(kpi, month, cfg.prorate_cumulative), kpi.direction, cfg),
    )
