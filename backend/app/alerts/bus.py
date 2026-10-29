"""In-process live push. One process serves everything (SQLite is single-writer), so a simple fan-out is enough.

Alerts are published only AFTER the transaction that created them commits, so a client is never told about
an alert that then rolls back. Each subscriber only receives alerts it may see (company scope) and wants
(severity, muted kinds, quiet hours).
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.security import Principal

from .prefs import Prefs, should_push

QUEUE_MAX = 100


@dataclass(eq=False)  # identity hashing: subscribers live in a set
class Subscriber:
    who: Principal
    prefs: Prefs
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_MAX))


_subs: set[Subscriber] = set()
_lock = threading.Lock()


def subscribe(who: Principal, prefs: Prefs, loop: asyncio.AbstractEventLoop) -> Subscriber:
    s = Subscriber(who, prefs, loop)
    with _lock:
        _subs.add(s)
    return s


def unsubscribe(s: Subscriber) -> None:
    with _lock:
        _subs.discard(s)


def prefs_changed(user_id: str, prefs: Prefs) -> None:
    """A user saved new preferences: their open streams pick them up immediately."""
    with _lock:
        for s in _subs:
            if s.who.user_id == user_id:
                s.prefs = prefs


def subscriber_count() -> int:
    with _lock:
        return len(_subs)


def _may_see(who: Principal, company_id: int | None) -> bool:
    return who.company_ids is None if company_id is None else who.can_see(company_id)


def _put(s: Subscriber, event_: dict) -> None:
    try:
        s.queue.put_nowait(event_)
    except asyncio.QueueFull:  # a stalled client must not hold memory; the feed and badge still have the alert
        pass


def publish(alert: dict, now: datetime | None = None) -> int:
    """Deliver to every subscriber who may see and wants this alert. Safe to call from any thread."""
    with _lock:
        targets = list(_subs)
    sent = 0
    for s in targets:
        if _may_see(s.who, alert.get("company_id")) and should_push(s.prefs, alert["severity"], alert["kind"], now):
            try:
                s.loop.call_soon_threadsafe(_put, s, alert)
                sent += 1
            except RuntimeError:  # that client's event loop has gone away
                unsubscribe(s)
    return sent


def serialize(a: Any) -> dict:
    return {"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "entity": a.entity,
            "company_id": a.company_id, "period": a.period}


def queue_for_publish(db: Session, alert: Any) -> None:
    """Called when an alert is created: remember it, and publish when (and only if) the transaction commits."""
    db.info.setdefault("pending_alerts", []).append(serialize(alert))


@event.listens_for(Session, "after_commit")
def _publish_committed(session: Session) -> None:
    for a in session.info.pop("pending_alerts", []):
        publish(a)


@event.listens_for(Session, "after_rollback")
def _forget_rolled_back(session: Session) -> None:
    # after_rollback also fires for a rolled-back SAVEPOINT; only drop the queue when the whole transaction is gone.
    if not session.in_transaction():
        session.info.pop("pending_alerts", None)
