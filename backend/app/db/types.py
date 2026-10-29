from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A timestamp that is always UTC and always timezone-aware in Python.

    SQLite (and some drivers) hand back naive datetimes, which then serialize with no zone: browsers
    read "2026-10-29T10:00:00" as LOCAL time, so every timestamp shows hours off. This makes the zone
    explicit on the way out ("...Z") and treats naive values as UTC on the way in.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
