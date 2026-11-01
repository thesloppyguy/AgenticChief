"""Fixture-backed workforce intelligence (pulse, skills, succession, draft actions)."""
from __future__ import annotations

from app.workforce.loader import (
    draft_actions,
    load_section,
    pulse,
    skills,
    succession,
)

__all__ = ["draft_actions", "load_section", "pulse", "skills", "succession"]
