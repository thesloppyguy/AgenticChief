"""Claim due jobs atomically, run them, record the outcome, and schedule the next run."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.alerts import engine as alerts_engine
from app.audit.logger import audit
from app.core.config import settings
from app.core.security import Principal, Role
from app.db.models import JobSchedule

from .cadence import next_after
from .jobs import JOBS, JobFailed

log = logging.getLogger(__name__)
SYSTEM = Principal("scheduler", Role.ADMIN, None)


def claim_due(factory: sessionmaker, now: datetime) -> list[int]:
    """Mark due, enabled, unclaimed jobs as in flight. The UPDATE ... WHERE is the lock: of two ticks that
    both see a job due, only one changes the row."""
    claimed: list[int] = []
    with factory() as db:
        for sid in db.scalars(select(JobSchedule.id).where(JobSchedule.enabled.is_(True),
                                                           JobSchedule.next_run_at <= now,
                                                           JobSchedule.claimed_at.is_(None))):
            n = db.execute(update(JobSchedule).where(JobSchedule.id == sid, JobSchedule.claimed_at.is_(None),
                                                     JobSchedule.next_run_at <= now)
                           .values(claimed_at=now)).rowcount
            db.commit()
            if n == 1:
                claimed.append(sid)
    return claimed


def run_one(factory: sessionmaker, schedule_id: int, now: datetime, deps: dict[str, Any]) -> str:
    """Run a claimed job. Always reschedules, whatever happened."""
    with factory() as db:
        s = db.get(JobSchedule, schedule_id)
        status, detail = "success", ""
        try:
            detail = JOBS[s.job](db, s.params or {}, now, deps)
        except JobFailed as e:
            db.rollback()
            status, detail = "failed", str(e)[:200]
        except Exception as e:  # noqa: BLE001 - the loop must survive any job; type only
            db.rollback()
            status, detail = "failed", f"unexpected error ({type(e).__name__})"
        s = db.get(JobSchedule, schedule_id)
        s.last_run_at, s.last_status, s.last_detail, s.claimed_at = now, status, detail, None
        s.next_run_at = next_after(s.cadence, now)
        audit(db, SYSTEM, "scheduled_job", f"{s.id}:{s.job}", {"status": status})
        if status == "failed":
            alerts_engine._raise(db, kind="scheduled_job_failed", severity="medium", company_id=None, entity=s.job,
                                 period=now.strftime("%Y-%m"), title=f"Scheduled job '{s.name}' failed: {detail}",
                                 detail={"schedule_id": s.id, "detail": detail},
                                 dedupe_key=f"job:{s.id}:{now.strftime('%Y-%m-%d')}")
        db.commit()
        return status


def tick(factory: sessionmaker, now: datetime, deps: dict[str, Any]) -> dict[int, str]:
    return {sid: run_one(factory, sid, now, deps) for sid in claim_due(factory, now)}


def release_orphans(factory: sessionmaker, now: datetime) -> int:
    """A job still 'in flight' long after it started was left by a crashed process: free it to run again."""
    cutoff = now - timedelta(seconds=settings.scheduler_claim_timeout_s)
    with factory() as db:
        n = db.execute(update(JobSchedule).where(JobSchedule.claimed_at.is_not(None), JobSchedule.claimed_at < cutoff)
                       .values(claimed_at=None)).rowcount
        db.commit()
    return n


def _proactive_tick(factory: sessionmaker) -> None:
    from app.scheduler.reminders import nudge_open_loops, send_due_reminders

    with factory() as db:
        try:
            n = send_due_reminders(db)
            if n:
                log.info("delivered %d reminder(s)", n)
        except Exception:
            log.exception("reminder tick failed")
            db.rollback()
        try:
            n = nudge_open_loops(db)
            if n:
                log.info("nudged %d open loop(s)", n)
        except Exception:
            log.exception("open-loop nudge failed")
            db.rollback()


async def loop(factory: sessionmaker, deps_factory) -> None:
    """The in-process scheduler. Runs the (blocking) tick in a worker thread so requests are not stalled."""
    await asyncio.to_thread(release_orphans, factory, datetime.now(UTC))
    while True:
        try:
            ran = await asyncio.to_thread(tick, factory, datetime.now(UTC), deps_factory())
            if ran:
                log.info("scheduled jobs ran: %s", ran)
            await asyncio.to_thread(_proactive_tick, factory)
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler_poll_s)
