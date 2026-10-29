from __future__ import annotations

from .models import ScoringConfig, Status


def status_for(score: float | None, cfg: ScoringConfig) -> Status | None:
    """Thresholds apply to the unrounded score."""
    if score is None:
        return None
    if score >= cfg.green_min:
        return Status.GREEN
    if score >= cfg.amber_min:
        return Status.AMBER
    return Status.RED
