from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker
from sse_starlette.sse import EventSourceResponse

from app.alerts import bus, prefs, store
from app.api.workflows import get_session_factory
from app.approvals.service import pending_count
from app.core.security import Principal, get_principal
from app.db.session import get_db

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
