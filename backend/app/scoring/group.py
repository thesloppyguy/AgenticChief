from __future__ import annotations

from .ic import score_ic
from .models import KpiDef, KpiValue, MissingICPolicy, OverallResult, ScoringConfig


def group_values(
    kpis: list[KpiDef], ic_values: dict[str, dict[str, KpiValue]], cfg: ScoringConfig
) -> dict[str, KpiValue]:
    """Group achievement per KPI: simple average of IC achievements.

    KPIs with `group_sum_of` (Cost per Hire) use total numerator / total denominator instead
    of averaging IC-level ratios.
    """
    out: dict[str, KpiValue] = {}
    for k in kpis:
        per_ic = [vals.get(k.key) for vals in ic_values.values()]
        if k.group_sum_of:
            num = sum(v.numerator for v in per_ic if v and v.numerator is not None)
            den = sum(v.denominator for v in per_ic if v and v.denominator is not None)
            out[k.key] = KpiValue(num / den if den else None, num, den)
            continue
        present = [v.achievement for v in per_ic if v and v.achievement is not None]
        if cfg.missing_ic_policy is MissingICPolicy.ZERO:
            n = len(per_ic)
            out[k.key] = KpiValue(sum(present) / n if n else None)
        else:
            out[k.key] = KpiValue(sum(present) / len(present) if present else None)
    return out


def score_group(
    kpis: list[KpiDef],
    ic_values: dict[str, dict[str, KpiValue]],
    month: int,
    cfg: ScoringConfig,
) -> OverallResult:
    return score_ic(kpis, group_values(kpis, ic_values, cfg), month, cfg)
