"""Ensure morning brief / EOD digest schedules exist."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import JobSchedule
from app.scheduler.cadence import next_after


def seed_principal_briefs(db: Session) -> int:
    created = 0
    specs = [
        (
            "morning_brief",
            "Morning brief",
            {"type": "daily", "time": f"{settings.morning_brief_hour:02d}:00"},
        ),
        (
            "end_of_day_digest",
            "End of day digest",
            {"type": "daily", "time": f"{settings.eod_digest_hour:02d}:00"},
        ),
    ]
    now = datetime.now(UTC)
    for job, name, cadence in specs:
        exists = db.scalar(select(JobSchedule.id).where(JobSchedule.job == job))
        if exists:
            continue
        try:
            nxt = next_after(cadence, now - timedelta(minutes=1))
        except Exception:
            nxt = now + timedelta(hours=1)
        db.add(
            JobSchedule(
                job=job,
                name=name,
                cadence=cadence,
                params={},
                enabled=True,
                next_run_at=nxt,
                created_by="system",
            )
        )
        created += 1
    if created:
        db.commit()
    return created
