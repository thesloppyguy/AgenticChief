from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.workflows import get_async_llm, get_llm, get_session_factory
from app.audit.logger import audit
from app.core.security import Principal, require_admin
from app.db.models import Asset, JobSchedule, Watch
from app.db.session import get_db
from app.ingestion.sources import SOURCE_KPIS
from app.scheduler import cadence as cad
from app.scheduler.jobs import JOBS
from app.scheduler.runner import run_one

router = APIRouter(prefix="/schedules")


def admin(who: Principal = Depends(require_admin)) -> Principal:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    return who


def _out(s: JobSchedule) -> dict:
    return {"id": s.id, "job": s.job, "name": s.name, "cadence": s.cadence, "params": s.params or {},
            "enabled": s.enabled, "next_run_at": s.next_run_at, "last_run_at": s.last_run_at,
            "last_status": s.last_status, "last_detail": s.last_detail, "running": s.claimed_at is not None}


# What each job accepts. A param that means nothing to a job is a mistake worth refusing, not ignoring.
PARAMS: dict[str, set[str]] = {
    "ingest": {"period", "sources"},
    "monthly_review": {"period"},
    "watch": {"period", "watch_id"},
    "workflow": {"period", "workflow_key"},
    "morning_brief": set(),
    "end_of_day_digest": set(),
}


def _clean(job: str, cadence: dict, params: dict | None, db: Session | None = None) -> tuple[dict, dict]:
    if job not in JOBS:
        raise HTTPException(422, f"job must be one of {', '.join(JOBS)}")
    try:
        c = cad.validate(cadence)
    except cad.CadenceError as e:
        raise HTTPException(422, str(e)) from e
    p = dict(params or {})
    extra = set(p) - PARAMS.get(job, set())
    if extra:
        raise HTTPException(422, f"unknown params for {job}: {', '.join(sorted(extra))}")
    period = p.get("period")
    if period is not None and period not in ("current", "previous") and not (
            isinstance(period, str) and len(period) == 7 and period[:4].isdigit() and period[4] == "-" and period[5:].isdigit()
            and 1 <= int(period[5:]) <= 12):
        raise HTTPException(422, "params.period must be current, previous or YYYY-MM")
    if "sources" in p and (not isinstance(p["sources"], list)
                           or set(p["sources"]) - (set(SOURCE_KPIS) | {"registry"})):
        raise HTTPException(422, "params.sources must be a list of known sources, and only applies to ingest")
    if job == "watch":
        wid = p.get("watch_id")
        if not isinstance(wid, int) or isinstance(wid, bool) or wid <= 0:
            raise HTTPException(422, "params.watch_id must name a watch")
        if db is not None and db.get(Watch, wid) is None:
            raise HTTPException(422, "params.watch_id must name a watch")
    if job == "workflow":
        key = p.get("workflow_key")
        a = db.scalar(select(Asset).where(Asset.kind == "workflow", Asset.key == key)) if db and key else None
        # Checked here too, so an unschedulable job fails fast rather than at 2am.
        if a is None or a.published_version is None or a.deprecated:
            raise HTTPException(422, "params.workflow_key must name a published workflow")
    return c, p


class ScheduleIn(BaseModel):
    job: str
    name: str = Field(min_length=1, max_length=120)
    cadence: dict
    params: dict | None = None
    enabled: bool = True


class SchedulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    cadence: dict | None = None
    params: dict | None = None
    enabled: bool | None = None


@router.get("")
def list_schedules(db: Session = Depends(get_db), _: Principal = Depends(admin)):
    return [_out(s) for s in db.scalars(select(JobSchedule).order_by(JobSchedule.id))]


@router.post("", status_code=201)
def create(body: ScheduleIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    c, p = _clean(body.job, body.cadence, body.params, db)
    s = JobSchedule(job=body.job, name=body.name, cadence=c, params=p, enabled=body.enabled,
                    next_run_at=cad.next_after(c, datetime.now(UTC)), created_by=who.user_id)
    db.add(s)
    audit(db, who, "schedule_created", f"{body.job}:{body.name}")
    db.commit()
    return _out(s)


@router.patch("/{schedule_id}")
def update_schedule(schedule_id: int, body: SchedulePatch, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    s = db.get(JobSchedule, schedule_id)
    if s is None:
        raise HTTPException(404, "Schedule not found")
    c, p = _clean(s.job, body.cadence or s.cadence,
                  body.params if body.params is not None else s.params, db)
    if body.name is not None:
        s.name = body.name
    if body.enabled is not None:
        s.enabled = body.enabled
    if body.cadence is not None:
        s.cadence, s.next_run_at = c, cad.next_after(c, datetime.now(UTC))
    s.params = p
    audit(db, who, "schedule_updated", f"{s.id}:{s.job}")
    db.commit()
    return _out(s)


@router.delete("/{schedule_id}", status_code=204)
def delete(schedule_id: int, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    s = db.get(JobSchedule, schedule_id)
    if s is None:
        raise HTTPException(404, "Schedule not found")
    audit(db, who, "schedule_deleted", f"{s.id}:{s.job}")
    db.delete(s)
    db.commit()


@router.post("/{schedule_id}/run-now")
def run_now(schedule_id: int, db: Session = Depends(get_db), who: Principal = Depends(admin),
            factory: sessionmaker = Depends(get_session_factory), llm=Depends(get_llm),
            allm=Depends(get_async_llm)):
    """Run it now and wait. Refused while the schedule is already running."""
    now = datetime.now(UTC)
    claimed = db.execute(update(JobSchedule).where(JobSchedule.id == schedule_id, JobSchedule.claimed_at.is_(None))
                         .values(claimed_at=now)).rowcount
    db.commit()
    if claimed != 1:
        raise HTTPException(409 if db.get(JobSchedule, schedule_id) else 404,
                            "That schedule is already running" if db.get(JobSchedule, schedule_id) else "Schedule not found")
    audit(db, who, "schedule_run_now", str(schedule_id))
    db.commit()
    status = run_one(factory, schedule_id, now, {"factory": factory, "llm": llm, "allm": allm})
    db.expire_all()
    return {"status": status, "schedule": _out(db.get(JobSchedule, schedule_id))}
