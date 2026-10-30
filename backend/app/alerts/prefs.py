"""Per-user alert preferences. The feed and the unread badge honour severity and muting; quiet hours only
silence live push (an urgent alert still gets through, and nothing is ever hidden from the feed by quiet hours)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.db.models import UserPrefs

SEVERITIES = ("low", "medium", "high", "urgent")
KINDS = ("status_red", "ingestion_failed", "capability_changed", "workflow_failed", "scheduled_job_failed",
         "watch_fired")


class PrefsError(ValueError):
    pass


@dataclass
class Prefs:
    min_severity: str = "low"
    muted_kinds: list[str] = field(default_factory=list)
    quiet_start: str | None = None
    quiet_end: str | None = None
    tz: str = "UTC"
    memory_enabled: bool = True


def get(db: Session, user_id: str) -> Prefs:
    r = db.get(UserPrefs, user_id)
    return Prefs() if r is None else Prefs(r.min_severity, list(r.muted_kinds or []), r.quiet_start, r.quiet_end, r.tz,
                                           r.memory_enabled)


def _hhmm(s: str) -> time:
    try:
        h, m = s.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError) as e:
        raise PrefsError("quiet hours must be HH:MM") from e


def validate(p: Prefs) -> Prefs:
    if p.min_severity not in SEVERITIES:
        raise PrefsError(f"min_severity must be one of {', '.join(SEVERITIES)}")
    bad = sorted(set(p.muted_kinds) - set(KINDS))
    if bad:
        raise PrefsError(f"unknown alert kinds: {', '.join(bad)}")
    if (p.quiet_start is None) != (p.quiet_end is None):
        raise PrefsError("set both quiet_start and quiet_end, or neither")
    if p.quiet_start is not None:
        _hhmm(p.quiet_start), _hhmm(p.quiet_end)  # type: ignore[arg-type]
        if p.quiet_start == p.quiet_end:
            raise PrefsError("quiet hours cannot start and end at the same time")
    try:
        ZoneInfo(p.tz)
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise PrefsError("tz must be an IANA timezone such as Asia/Kolkata") from e
    p.muted_kinds = sorted(set(p.muted_kinds))
    return p


def save(db: Session, user_id: str, p: Prefs) -> Prefs:
    validate(p)
    r = db.get(UserPrefs, user_id)
    if r is None:
        r = UserPrefs(user_id=user_id)
        db.add(r)
    r.min_severity, r.muted_kinds, r.quiet_start, r.quiet_end, r.tz, r.memory_enabled = (
        p.min_severity, p.muted_kinds, p.quiet_start, p.quiet_end, p.tz, p.memory_enabled)
    db.commit()
    return p


def visible(p: Prefs, severity: str, kind: str) -> bool:
    """Does this alert belong in the user's feed and unread count?"""
    return kind not in p.muted_kinds and SEVERITIES.index(severity) >= SEVERITIES.index(p.min_severity)


def is_quiet(p: Prefs, now: datetime) -> bool:
    if p.quiet_start is None or p.quiet_end is None:
        return False
    local = now.astimezone(ZoneInfo(p.tz)).time().replace(second=0, microsecond=0)
    start, end = _hhmm(p.quiet_start), _hhmm(p.quiet_end)
    return start <= local < end if start < end else (local >= start or local < end)  # overnight windows wrap midnight


def should_push(p: Prefs, severity: str, kind: str, now: datetime | None = None) -> bool:
    """Live push: visible to the user, and not in quiet hours unless it is urgent."""
    if not visible(p, severity, kind):
        return False
    return severity == "urgent" or not is_quiet(p, now or datetime.now(UTC))
