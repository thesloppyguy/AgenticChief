"""Admin-editable scoring rules. Validated strictly: a bad rule set must never reach the engine."""
from __future__ import annotations

from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.kpi_registry.seed import DEFAULT_CONFIG, KPIS, PILLAR_LABELS, PILLAR_WEIGHTS
from app.scoring.models import KpiDef, MissingICPolicy, ScoringConfig

_BY_KEY = {k.key: k for k in KPIS}


class KpiOverride(BaseModel):
    """A change to one KPI's weight inside its pillar and/or its target. Anything left out keeps its default."""

    weight: float | None = Field(default=None, gt=0, le=1)
    target: float | None = Field(default=None, gt=0)


def effective_kpis(overrides: dict[str, KpiOverride | dict]) -> list[KpiDef]:
    """The 23 KPI definitions with the overrides applied."""
    out = []
    for k in KPIS:
        o = overrides.get(k.key)
        o = KpiOverride(**o) if isinstance(o, dict) else o
        out.append(replace(k, **{**({"weight": o.weight} if o and o.weight is not None else {}),
                                 **({"target": o.target} if o and o.target is not None else {})}) if o else k)
    return out


class ScorecardRules(BaseModel):
    pillar_weights: dict[str, float] = Field(default_factory=lambda: dict(PILLAR_WEIGHTS))
    green_min: float = Field(default=DEFAULT_CONFIG.green_min, ge=0, le=1000)
    amber_min: float = Field(default=DEFAULT_CONFIG.amber_min, ge=0, le=1000)
    score_cap: float | None = Field(default=None, gt=0, le=1000, description="None = scores may exceed 100")
    zero_lower_is_better_score: float = Field(default=DEFAULT_CONFIG.zero_lower_is_better_score, ge=0, le=1000)
    missing_ic_policy: Literal["exclude", "zero"] = "exclude"
    min_coverage_for_status: float = Field(default=0.0, ge=0, le=1)
    prorate_cumulative: bool = False
    kpi_overrides: dict[str, KpiOverride] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> ScorecardRules:
        if set(self.pillar_weights) != set(PILLAR_WEIGHTS):
            raise ValueError("pillar_weights must name exactly the 7 pillars")
        if any(w <= 0 for w in self.pillar_weights.values()):
            raise ValueError("every pillar weight must be above zero")
        if abs(sum(self.pillar_weights.values()) - 1.0) > 1e-6:
            raise ValueError(f"pillar weights must add up to 100% (they add up to {sum(self.pillar_weights.values()) * 100:g}%)")
        if self.amber_min >= self.green_min:
            raise ValueError("amber_min must be below green_min")
        if self.score_cap is not None and self.score_cap < self.green_min:
            raise ValueError("score_cap below green_min would make green unreachable")
        if self.score_cap is not None and self.zero_lower_is_better_score > self.score_cap:
            raise ValueError("zero_lower_is_better_score cannot exceed score_cap")
        for key, o in self.kpi_overrides.items():
            if key not in _BY_KEY:
                raise ValueError(f"unknown KPI '{key}'")
            if o.target is not None and _BY_KEY[key].target_steps:
                raise ValueError(f"{key}: its target follows a calendar rule (April / October) and cannot be overridden")
            if o.weight is None and o.target is None:
                raise ValueError(f"{key}: an override must change the weight or the target")
        for pillar in PILLAR_WEIGHTS:  # every pillar's KPI weights must still add up to 100%
            total = sum(k.weight for k in effective_kpis(self.kpi_overrides) if k.pillar == pillar)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"{PILLAR_LABELS[pillar]}: KPI weights add up to {total * 100:g}%, not 100%")
        return self


DEFAULT_RULES = ScorecardRules()


def to_scoring_config(rules: ScorecardRules, version: int, no_source: frozenset[str] = frozenset()) -> ScoringConfig:
    return ScoringConfig(
        pillar_weights=dict(rules.pillar_weights), green_min=rules.green_min, amber_min=rules.amber_min,
        score_cap=rules.score_cap, zero_lower_is_better_score=rules.zero_lower_is_better_score,
        missing_ic_policy=MissingICPolicy(rules.missing_ic_policy), no_source=no_source,
        min_coverage_for_status=rules.min_coverage_for_status, prorate_cumulative=rules.prorate_cumulative,
        version=str(version))
