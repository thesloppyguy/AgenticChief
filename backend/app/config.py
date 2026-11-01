"""OpenExecutive-style settings accessor used by ported agent modules."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, settings as _settings


@lru_cache
def get_settings() -> Settings:
    return _settings
