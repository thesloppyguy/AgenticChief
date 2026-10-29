"""Pure data types for the scoring engine. No I/O, no LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Direction(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"


class Status(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class MissingICPolicy(StrEnum):
    EXCLUDE = "exclude"  # ICs without a value are left out of the group average
    ZERO = "zero"  # ICs without a value count as 0


@dataclass(frozen=True)
class KpiDef:
    key: str
    pillar: str
    weight: float  # fraction within the pillar (0-1)
    direction: Direction
    target: float
    due_from_month: int | None = None  # calendar month (1-12) the KPI is first scored
    target_steps: tuple[tuple[int, float], ...] = ()  # (from calendar month, target), fiscal order
    group_sum_of: tuple[str, str] | None = None  # (numerator key, denominator key) e.g. cost/hires
    cumulative: bool = False  # a year-to-date count scored against a full-year target (see prorate_cumulative)


@dataclass(frozen=True)
class KpiValue:
    """One IC's value for one KPI in one period. `achievement=None` means no value."""

    achievement: float | None
    numerator: float | None = None
    denominator: float | None = None


@dataclass(frozen=True)
class ScoringConfig:
    pillar_weights: dict[str, float]
    green_min: float = 90.0
    amber_min: float = 75.0
    score_cap: float | None = None  # None = uncapped; PRD leaves this open
    zero_lower_is_better_score: float = 100.0  # target/0 is undefined; configurable
    missing_ic_policy: MissingICPolicy = MissingICPolicy.EXCLUDE
    # KPIs whose source capability is unmapped in this deployment. Excluded and rescaled, like a
    # not-yet-due KPI, but reported as "No source" rather than missing. Runtime state, not scoring policy.
    no_source: frozenset[str] = frozenset()
    # Show no status (green/amber/red) when less than this share of the scorecard weight could be scored.
    min_coverage_for_status: float = 0.0
    # Score year-to-date KPIs against target x months-elapsed/12, so early in the year they are not "red".
    prorate_cumulative: bool = False
    version: str = "1"


@dataclass(frozen=True)
class KpiResult:
    key: str
    score: float | None
    excluded_reason: str | None = None  # "missing" | "not_due" | "no_source" | None


@dataclass(frozen=True)
class PillarResult:
    pillar: str
    score: float | None
    kpis: list[KpiResult] = field(default_factory=list)
    eligible_weight: float = 0.0


@dataclass(frozen=True)
class OverallResult:
    score: float | None
    status: Status | None
    pillars: list[PillarResult]
    pillar_coverage: float  # share of pillar weight that was scoreable
    status_withheld: bool = False  # a score exists but coverage was too low to give it a status
