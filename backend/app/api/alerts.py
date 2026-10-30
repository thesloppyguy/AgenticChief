from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker
from sse_starlette.sse import EventSourceResponse

from app.alerts import bus, prefs, store, watches
from app.api.workflows import get_session_factory
from app.approvals.service import pending_count
from app.audit.logger import audit
from app.core.security import Principal, get_principal
from app.db.session import get_db
from app.services.scorecard import current_period

router = APIRouter()


@router.get("/alerts")
def alerts(unread_only: bool = False, limit: int = 100, include_hidden: bool = False, db: Session = Depends(get_db),
           who: Principal = Depends(get_principal)):
    """`include_hidden` also lists alerts your preferences (minimum severity, muted kinds) would hide."""
    return store.list_alerts(db, who, unread_only, limit, include_hidden)


@router.post("/alerts/read-all")
def read_all(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    return {"marked": store.mark_all_read(db, who)}


@router.post("/alerts/{alert_id}/read")
def read(alert_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    if not store.mark_read(db, who, alert_id):
        raise HTTPException(404, "Alert not found")
    return {"ok": True}


@router.get("/unread/summary")
def unread_summary(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    return {"alerts": store.unread_count(db, who), "approvals_pending": pending_count(db, who)}


@router.get("/alerts/stream")
async def stream(who: Principal = Depends(get_principal), factory: sessionmaker = Depends(get_session_factory)):
    """Live alerts as server-sent events. Only alerts you may see and your preferences allow are sent."""
    def load() -> prefs.Prefs:
        with factory() as db:
            return prefs.get(db, who.user_id)

    sub = bus.subscribe(who, await asyncio.to_thread(load), asyncio.get_running_loop())

    async def events():
        try:
            yield {"event": "ready", "data": "{}"}
            while True:
                yield {"event": "alert", "data": json.dumps(await sub.queue.get())}
        finally:  # the client went away (or the server is stopping)
            bus.unsubscribe(sub)

    return EventSourceResponse(events(), ping=15)


class PrefsIn(BaseModel):
    min_severity: str = "low"
    muted_kinds: list[str] = Field(default_factory=list)
    quiet_start: str | None = None
    quiet_end: str | None = None
    tz: str = "UTC"


@router.get("/alert-prefs")
def get_prefs(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    p = prefs.get(db, who.user_id)
    return {"min_severity": p.min_severity, "muted_kinds": p.muted_kinds, "quiet_start": p.quiet_start,
            "quiet_end": p.quiet_end, "tz": p.tz, "known_kinds": list(prefs.KINDS), "severities": list(prefs.SEVERITIES)}


@router.put("/alert-prefs")
def put_prefs(body: PrefsIn, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    current = prefs.get(db, who.user_id)
    new = prefs.Prefs(body.min_severity, body.muted_kinds, body.quiet_start, body.quiet_end, body.tz, current.memory_enabled)
    try:
        saved = prefs.save(db, who.user_id, new)
    except prefs.PrefsError as e:
        raise HTTPException(422, str(e)) from e
    bus.prefs_changed(who.user_id, saved)
    return get_prefs(db, who)


# --- watches ------------------------------------------------------------------------------------
# A watch is personal: its owner defines the condition and only its owner is alerted. It lives here,
# not on /schedules, because that router is admin + group-wide and a scoped viewer may own a watch.


class WatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company_code: str | None = None  # None = the Group, which needs group-wide access
    condition: dict
    cadence: dict
    enabled: bool = True


class WatchPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    condition: dict | None = None
    cadence: dict | None = None
    enabled: bool | None = None


def _watch_http(e: watches.WatchError) -> HTTPException:
    return HTTPException(e.status, e.message)


@router.get("/watches")
def list_watches(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    return [watches.out(db, w) for w in watches.listing(db, who)]


@router.post("/watches", status_code=201)
def create_watch(body: WatchIn, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    try:
        w = watches.create(db, who, body.name, body.company_code, body.condition, body.cadence, body.enabled)
    except watches.WatchError as e:
        raise _watch_http(e) from e
    audit(db, who, "watch_created", f"{w.id}:{w.name}")
    db.commit()
    return watches.out(db, w)


@router.patch("/watches/{watch_id}")
def update_watch(watch_id: int, body: WatchPatch, db: Session = Depends(get_db),
                 who: Principal = Depends(get_principal)):
    try:
        w = watches.update(db, who, watch_id, body.name, body.condition, body.cadence, body.enabled)
    except watches.WatchError as e:
        raise _watch_http(e) from e
    audit(db, who, "watch_updated", str(watch_id))
    db.commit()
    return watches.out(db, w)


@router.delete("/watches/{watch_id}", status_code=204)
def delete_watch(watch_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    try:
        watches.delete(db, who, watch_id)
    except watches.WatchError as e:
        raise _watch_http(e) from e
    audit(db, who, "watch_deleted", str(watch_id))
    db.commit()


@router.post("/watches/{watch_id}/test")
def test_watch(watch_id: int, period: str | None = None, db: Session = Depends(get_db),
               who: Principal = Depends(get_principal)):
    """Evaluate now without raising anything. A watch's failure mode is silence, so being able to
    see what it currently observes is what makes one trustworthy."""
    try:
        w = watches.owned(db, who, watch_id)
        return watches.observe(db, w, period or current_period())
    except watches.WatchError as e:
        raise _watch_http(e) from e
