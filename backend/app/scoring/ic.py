from __future__ import annotations

from .models import KpiDef, KpiValue, OverallResult, ScoringConfig
from .pillar import score_pillar
from .status import status_for


def score_ic(
    kpis: list[KpiDef], values: dict[str, KpiValue], month: int, cfg: ScoringConfig
) -> OverallResult:
    pillars = [score_pillar(p, kpis, values, month, cfg) for p in cfg.pillar_weights]
    eligible = [p for p in pillars if p.score is not None]
    total = sum(cfg.pillar_weights[p.pillar] for p in eligible)
    coverage = total / sum(cfg.pillar_weights.values())
    if total == 0:
        return OverallResult(None, None, pillars, 0.0)
    score = sum(p.score * cfg.pillar_weights[p.pillar] for p in eligible) / total  # type: ignore[operator]
    withheld = coverage < cfg.min_coverage_for_status  # a score on thin evidence gets no green/amber/red
    return OverallResult(score, None if withheld else status_for(score, cfg), pillars, coverage, withheld)
