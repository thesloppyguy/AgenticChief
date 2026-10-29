"""When a scheduled job next runs. Everything is UTC, and every function takes `now` explicitly."""
from __future__ import annotations

import calendar
import re
from datetime import UTC, datetime, timedelta

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class CadenceError(ValueError):
    pass


def validate(c: dict) -> dict:
    kind = c.get("type")
    if kind not in ("daily", "weekly", "monthly"):
        raise CadenceError("cadence.type must be daily, weekly or monthly")
    if not isinstance(c.get("time"), str) or not _TIME.match(c["time"]):
        raise CadenceError("cadence.time must be HH:MM (24-hour, UTC)")
    out = {"type": kind, "time": c["time"]}
    if kind == "weekly":
        if not isinstance(c.get("weekday"), int) or not 0 <= c["weekday"] <= 6:
            raise CadenceError("cadence.weekday must be 0 (Monday) to 6 (Sunday)")
        out["weekday"] = c["weekday"]
    if kind == "monthly":
        # Capped at 28 so every month has the day: a job on "the 31st" would silently skip months.
        if not isinstance(c.get("day"), int) or not 1 <= c["day"] <= 28:
            raise CadenceError("cadence.day must be 1 to 28")
        out["day"] = c["day"]
    return out


def next_after(c: dict, after: datetime) -> datetime:
    """The first run time strictly after `after`."""
    after = after.astimezone(UTC)
    hh, mm = map(int, c["time"].split(":"))
    at = lambda d: d.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if c["type"] == "daily":
        t = at(after)
        return t if t > after else t + timedelta(days=1)
    if c["type"] == "weekly":
        t = at(after) + timedelta(days=(c["weekday"] - after.weekday()) % 7)
        return t if t > after else t + timedelta(days=7)
    year, month = after.year, after.month
    t = at(after.replace(day=c["day"]))
    if t > after:
        return t
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    assert c["day"] <= calendar.monthrange(year, month)[1]
    return at(datetime(year, month, c["day"], tzinfo=UTC))
