"""User-defined watches: a condition over the scorecard, checked on a cadence, raising one alert.

Scores here are always *scores* (percent of target), not raw achievements, so one threshold means the
same thing whether it is watching the Group, a pillar or a single KPI.

Evaluation runs as SYSTEM because a scheduler thread has no JWT. That is safe because the watch's
company was checked against its owner's scope when it was created, and because the alert carries both
`company_id` and `audience_user_id` — so if the owner later loses access, the existing visibility
rules in `store`/`bus` suppress it anyway.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, Role
from app.db.models import Alert, Company, JobSchedule, Watch
from app.kpi_registry.seed import PILLAR_LABELS, PILLAR_WEIGHTS
from app.services.scorecard import active_kpis, build_scorecard

from . import engine as alerts_engine

SYSTEM = Principal("system", Role.ADMIN, None)
NUMERIC = ("overall", "pillar", "kpi")
KIND = "watch_fired"


class WatchError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class WatchCondition(BaseModel):
    """`equals` is deliberately not offered for a numeric subject: floats never compare equal, so such
    a watch would look valid and silently never fire."""

    subject: Literal["overall", "pillar", "kpi", "status"]
    pillar: str | None = None
    kpi_key: str | None = None
    comparator: Literal["below", "above", "equals", "changes_to"]
    threshold: float | None = Field(default=None, ge=0, le=1000)
    value: Literal["red", "amber", "green"] | None = None

    @model_validator(mode="after")
    def _check(self) -> WatchCondition:
        if self.subject in NUMERIC:
            if self.comparator not in ("below", "above"):
                raise ValueError("a score can only be watched with 'below' or 'above'")
            if self.threshold is None:
                raise ValueError("threshold is required for a score")
            if self.value is not None:
                raise ValueError("value applies to a status, not a score")
        else:
            if self.comparator not in ("equals", "changes_to"):
                raise ValueError("a status can only be watched with 'equals' or 'changes_to'")
            if self.value is None:
                raise ValueError("value is required for a status")
            if self.threshold is not None:
                raise ValueError("threshold applies to a score, not a status")
        if (self.subject == "pillar") != (self.pillar is not None):
            raise ValueError("pillar is required for, and only for, a pillar watch")
        if (self.subject == "kpi") != (self.kpi_key is not None):
            raise ValueError("kpi_key is required for, and only for, a KPI watch")
        if self.pillar is not None and self.pillar not in PILLAR_WEIGHTS:
            raise ValueError(f"unknown pillar '{self.pillar}'")
        return self

    def describe(self) -> str:
        what = {"overall": "overall score", "status": "status",
                "pillar": f"{PILLAR_LABELS.get(self.pillar or '', self.pillar)} score",
                "kpi": f"{(self.kpi_key or '').replace('_', ' ')} score"}[self.subject]
        if self.subject in NUMERIC:
            return f"{what} {self.comparator} {self.threshold:g}"
        return f"{what} {'is' if self.comparator == 'equals' else 'changes to'} {self.value}"


def parse(raw: dict) -> WatchCondition:
    try:
        return WatchCondition(**raw)
    except ValueError as e:
        raise WatchError(422, str(e).split("\n")[-1].strip()) from e


def check_known(db: Session, c: WatchCondition) -> None:
    """KPI membership depends on the active rules, so it is checked here rather than in the model
    (which stays pure, as app/assets/definitions.py does)."""
    if c.kpi_key and c.kpi_key not in {k.key for k in active_kpis(db)}:
        raise WatchError(422, f"unknown KPI '{c.kpi_key}'")


# --- evaluation -------------------------------------------------------------------------------

def _side(card: dict, company_id: int | None) -> dict | None:
    if company_id is None:
        return card["group"]
    return next((c for c in card["companies"] if c["company_id"] == company_id), None)


def reading(card: dict, w: Watch, c: WatchCondition) -> float | str | None:
    """The one number (or status) this watch is about, or None when there is nothing to compare."""
    side = _side(card, w.company_id)
    if side is None:
        return None
    if c.subject == "overall":
        return side["score"]
    if c.subject == "status":
        return side["status"]
    if c.subject == "pillar":
        p = next((p for p in side["pillars"] if p["pillar"] == c.pillar), None)
        return p["score"] if p else None
    for p in side["pillars"]:
        for k in p["kpis"]:
            if k["key"] == c.kpi_key:
                return k["score"]
    return None


def fires(c: WatchCondition, now_val, prev_val) -> bool:
    if now_val is None:  # no data is not a breach
        return False
    if c.subject in NUMERIC:
        return now_val < c.threshold if c.comparator == "below" else now_val > c.threshold
    if c.comparator == "equals":
        return now_val == c.value
    # changes_to asks about a transition, so it needs a previous reading to compare against. There is
    # none in April (a new fiscal year) or when last month had no data; claiming a change we cannot
    # see would be wrong. Someone who wants "tell me whenever it IS red" wants `equals`.
    if prev_val is None:
        return False
    return now_val == c.value and prev_val != c.value


def observe(db: Session, w: Watch, period: str) -> dict:
    """What this watch sees right now. Shared by the scheduled job and the /test endpoint, so what a
    user previews is exactly what will later fire."""
    c = parse(w.condition)
    now_val = reading(build_scorecard(db, SYSTEM, period), w, c)
    prev_val = None
    if c.comparator == "changes_to":
        prev = alerts_engine.prev_period(period)  # None in April: a new fiscal year starts fresh
        prev_val = reading(build_scorecard(db, SYSTEM, prev), w, c) if prev else None
    return {"would_fire": fires(c, now_val, prev_val), "observed": now_val, "previous": prev_val,
            "condition": c.describe()}


def evaluate(db: Session, w: Watch, period: str) -> Alert | None:
    """Raise at most one alert per watch per period. Does not commit: the caller owns the transaction."""
    seen = observe(db, w, period)
    if not seen["would_fire"]:
        return None
    code = db.scalar(select(Company.code).where(Company.id == w.company_id)) if w.company_id else None
    shown = seen["observed"]
    now = f"{shown:.1f}" if isinstance(shown, float) else str(shown)
    return alerts_engine._raise(
        db, kind=KIND,
        # A status breach is a settled fact; a threshold crossing is a number worth a look.
        severity="high" if parse(w.condition).subject == "status" else "medium",
        company_id=w.company_id, entity=code or "group", period=period,
        title=f"Watch '{w.name}': {code or 'Group'} {seen['condition']} (now {now})"[:200],
        detail={"watch_id": w.id, "observed": shown, "previous": seen["previous"],
                "condition": w.condition},
        # The value must not be in the key, or a drifting score re-alerts on every tick.
        dedupe_key=f"watch:{w.id}:{period}",
        audience_user_id=w.user_id)


# --- CRUD -------------------------------------------------------------------------------------

def _company(db: Session, who: Principal, code: str | None) -> int | None:
    if code is None:
        if who.company_ids is not None:
            raise WatchError(403, "a group-wide watch needs group-wide access")
        return None
    cid = db.scalar(select(Company.id).where(Company.code == code))
    # Unknown and out-of-scope look the same, so a watch cannot be used to enumerate companies.
    if cid is None or not who.can_see(cid):
        raise WatchError(403, "that company is unknown or out of your scope")
    return cid


def owned(db: Session, who: Principal, watch_id: int) -> Watch:
    w = db.get(Watch, watch_id)
    if w is None or (w.user_id != who.user_id and who.role is not Role.ADMIN):
        raise WatchError(404, "watch not found")
    return w


def create(db: Session, who: Principal, name: str, company_code: str | None, condition: dict,
           cadence: dict, enabled: bool = True) -> Watch:
    from app.scheduler import cadence as cad

    c = parse(condition)
    check_known(db, c)
    company_id = _company(db, who, company_code)
    try:
        clean = cad.validate(cadence)
    except cad.CadenceError as e:
        raise WatchError(422, str(e)) from e

    w = Watch(user_id=who.user_id, name=name, company_id=company_id,
              condition=c.model_dump(), enabled=enabled)
    db.add(w)
    db.flush()
    # The cadence lives on a paired schedule so watches inherit claiming and crash recovery.
    s = JobSchedule(job="watch", name=f"watch: {name}"[:120], cadence=clean,
                    params={"watch_id": w.id, "period": "current"}, enabled=enabled,
                    next_run_at=cad.next_after(clean, _now()), created_by=who.user_id)
    db.add(s)
    db.flush()
    w.schedule_id = s.id
    db.commit()
    return w


def update(db: Session, who: Principal, watch_id: int, name: str | None, condition: dict | None,
           cadence: dict | None, enabled: bool | None) -> Watch:
    from app.scheduler import cadence as cad

    w = owned(db, who, watch_id)
    s = db.get(JobSchedule, w.schedule_id) if w.schedule_id else None
    if condition is not None:
        c = parse(condition)
        check_known(db, c)
        w.condition = c.model_dump()
    if name is not None:
        w.name = name
        if s:
            s.name = f"watch: {name}"[:120]
    if enabled is not None:
        w.enabled = enabled
        if s:
            s.enabled = enabled
    if cadence is not None and s:
        try:
            s.cadence = cad.validate(cadence)
        except cad.CadenceError as e:
            raise WatchError(422, str(e)) from e
        s.next_run_at = cad.next_after(s.cadence, _now())
    db.commit()
    return w


def delete(db: Session, who: Principal, watch_id: int) -> None:
    w = owned(db, who, watch_id)
    schedule_id = w.schedule_id
    db.delete(w)  # the watch references the schedule, so it must go first
    db.flush()
    if schedule_id and (s := db.get(JobSchedule, schedule_id)):
        db.delete(s)
    db.commit()


def listing(db: Session, who: Principal) -> list[Watch]:
    q = select(Watch).order_by(Watch.id.desc())
    if who.role is not Role.ADMIN:
        q = q.where(Watch.user_id == who.user_id)
    return list(db.scalars(q))


def out(db: Session, w: Watch) -> dict:
    s = db.get(JobSchedule, w.schedule_id) if w.schedule_id else None
    return {"id": w.id, "name": w.name, "user_id": w.user_id, "company_id": w.company_id,
            "company_code": db.scalar(select(Company.code).where(Company.id == w.company_id))
            if w.company_id else None,
            "condition": w.condition, "describes": parse(w.condition).describe(), "enabled": w.enabled,
            "cadence": s.cadence if s else None, "next_run_at": s.next_run_at if s else None,
            "last_run_at": s.last_run_at if s else None, "last_status": s.last_status if s else None,
            "schedule_id": w.schedule_id, "created_at": w.created_at}


def _now() -> datetime:
    return datetime.now(UTC)
