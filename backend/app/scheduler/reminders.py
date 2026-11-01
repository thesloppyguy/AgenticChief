"""Claim due reminders and overdue open-loop nudges → in-app alerts."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.alerts.engine import _raise
from app.db.models import OpenLoop, Reminder
from app.services.scorecard import current_period

logger = logging.getLogger(__name__)


def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    period = current_period()
    due_ids = list(
        db.scalars(
            select(Reminder.id)
            .where(
                Reminder.sent_at.is_(None),
                Reminder.cancelled_at.is_(None),
                Reminder.claimed_at.is_(None),
                Reminder.due_at <= now,
            )
            .order_by(Reminder.due_at)
            .limit(20)
        )
    )
    n = 0
    for rid in due_ids:
        claimed = db.execute(
            update(Reminder)
            .where(
                Reminder.id == rid,
                Reminder.claimed_at.is_(None),
                Reminder.sent_at.is_(None),
            )
            .values(claimed_at=now)
        ).rowcount
        if claimed != 1:
            continue
        row = db.get(Reminder, rid)
        if row is None:
            continue
        _raise(
            db,
            kind="reminder",
            severity="medium",
            company_id=None,
            entity="reminder",
            period=period,
            title=f"Reminder: {row.text[:120]}",
            detail={"reminder_id": rid, "text": row.text, "due_at": str(row.due_at)},
            dedupe_key=f"reminder:{rid}",
            audience_user_id=row.user_id,
        )
        row.sent_at = now
        n += 1
    if n:
        db.commit()
    return n


def nudge_open_loops(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    period = current_period()
    overdue = list(
        db.scalars(
            select(OpenLoop)
            .where(
                OpenLoop.status == "open",
                OpenLoop.due_at.is_not(None),
                OpenLoop.due_at <= now,
            )
            .limit(30)
        )
    )
    n = 0
    for loop in overdue:
        if loop.last_nudged_at and loop.last_nudged_at > now - timedelta(hours=20):
            continue
        alert = _raise(
            db,
            kind="open_loop",
            severity="medium",
            company_id=None,
            entity="open_loop",
            period=period,
            title=f"Open loop overdue: {loop.description[:120]}",
            detail={"open_loop_id": loop.id, "description": loop.description},
            dedupe_key=f"open_loop:{loop.id}:{now.date().isoformat()}",
            audience_user_id=loop.user_id,
        )
        if alert is not None:
            loop.last_nudged_at = now
            n += 1
    if n:
        db.commit()
    return n
