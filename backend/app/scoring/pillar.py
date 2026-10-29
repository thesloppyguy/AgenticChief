from __future__ import annotations

from .kpi import score_kpi
from .models import KpiDef, KpiValue, PillarResult, ScoringConfig


def score_pillar(
    pillar: str,
    kpis: list[KpiDef],
    values: dict[str, KpiValue],
    month: int,
    cfg: ScoringConfig,
) -> PillarResult:
    results = [score_kpi(k, values.get(k.key), month, cfg) for k in kpis if k.pillar == pillar]
    weights = {k.key: k.weight for k in kpis if k.pillar == pillar}
    eligible = [r for r in results if r.score is not None]
    total = sum(weights[r.key] for r in eligible)
    if total == 0:
        return PillarResult(pillar, None, results, 0.0)
    score = sum(r.score * weights[r.key] for r in eligible) / total  # type: ignore[operator]
    return PillarResult(pillar, score, results, total)
