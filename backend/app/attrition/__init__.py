"""IC attrition sync (ICHRATTRITION CPI → local store)."""

from .sync import sync_attrition, attrition_status

__all__ = ["sync_attrition", "attrition_status"]
