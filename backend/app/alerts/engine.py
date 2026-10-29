"""Raise alerts from scorecard status changes and ingestion failures.

Rule-based triage: a change to red is an alert; severity depends on where it came from.
Dedupe is a unique key per (kind, entity, period), so re-evaluating a period never repeats an alert.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal, Role
from app.db.models import Alert
from app.ingestion.runner import SourceSummary
from app.ingestion.sources import SOURCE_LABELS
from app.services.scorecard import build_scorecard

from . import bus

log = logging.getLogger(__name__)
SYSTEM = Principal("system", Role.ADMIN, None)


def prev_period(period: str) -> str | None:
    """Previous month in the same April-March year; None for April (a new year starts fresh)."""
    y, m = map(int, period.split("-"))
    if m == 4:
        return None
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _raise(db: Session, **kw) -> Alert | None:
    exists = db.scalar(select(Alert.id).where(Alert.dedupe_key == kw["dedupe_key"]))
    if exists:
        return None
    alert = Alert(**kw)
    try:
        with db.begin_nested():
            db.add(alert)
    except IntegrityError:  # lost a race with another evaluator: the alert exists
        return None
    bus.queue_for_publish(db, alert)  # goes out live when this transaction commits
    return alert


def _weakest(pillars: list[dict], n: int = 2) -> list[dict]:
    scored = [p for p in pillars if p["score"] is not None]
    return [{"pillar": p["pillar"], "score": round(p["score"], 1)}
            for p in sorted(scored, key=lambda p: p["score"])[:n]]


def evaluate_period(db: Session, period: str, only_company_ids: list[int] | None = None) -> list[Alert]:
    """Compare this period's statuses with last month's and alert on anything that turned red."""
    now = build_scorecard(db, SYSTEM, period)
    prev_p = prev_period(period)
    before = build_scorecard(db, SYSTEM, prev_p) if prev_p else None
    prev_status: dict[str, str | None] = {}
    if before:
        prev_status = {"group": before["group"]["status"],
                       **{c["code"]: c["status"] for c in before["companies"]}}
    created: list[Alert] = []

    def consider(entity: str, company_id: int | None, status, score, pillars, urgent: bool):
        if status != "red":
            return
        prev = prev_status.get(entity)
        if prev == "red":
            return  # already red last month: not a change
        if prev is None:
            severity, how = ("high" if urgent else "low"), "is red (first reading this year)"
        elif prev == "green":
            severity, how = ("urgent" if urgent else "high"), "turned red (was green)"
        else:
            severity, how = ("urgent" if urgent else "medium"), "turned red (was amber)"
        name = "Group" if entity == "group" else entity
        a = _raise(
            db, kind="status_red", severity=severity, company_id=company_id, entity=entity, period=period,
            title=f"{name} {how}: {score:.1f}",
            detail={"score": round(score, 1), "previous_status": prev, "weakest_pillars": _weakest(pillars),
                    "synthetic": now["synthetic_data"]},
            dedupe_key=f"status_red:{entity}:{period}")
        if a:
            created.append(a)

    g = now["group"]
    if only_company_ids is None and g["score"] is not None:
        consider("group", None, g["status"], g["score"], g["pillars"], urgent=True)
    for c in now["companies"]:
        if c["score"] is None or (only_company_ids is not None and c["company_id"] not in only_company_ids):
            continue
        consider(c["code"], c["company_id"], c["status"], c["score"], c["pillars"], urgent=False)
    db.commit()
    return created


def on_ingestion(db: Session, summaries: list[SourceSummary], period: str) -> list[Alert]:
    created: list[Alert] = []
    for s in summaries:
        if s.status not in ("failed", "partial"):
            continue
        n = s.companies_ok + s.companies_failed
        a = _raise(
            db, kind="ingestion_failed", severity="high" if s.status == "failed" else "medium",
            company_id=None, entity=s.source, period=period,
            title=f"{SOURCE_LABELS.get(s.source, s.source)} ingestion {s.status} for {period}: "
                  f"{s.companies_failed} of {n} companies failed",
            detail={"mode": s.mode, "failed": s.companies_failed, "ok": s.companies_ok, "run_id": s.run_id},
            dedupe_key=f"ingestion:{s.run_id}")
        if a:
            created.append(a)
    db.commit()
    return created


def safe_evaluate(db: Session, period: str, only_company_ids: list[int] | None = None) -> None:
    """For request paths: alerting must never break the operation that triggered it."""
    try:
        evaluate_period(db, period, only_company_ids)
    except Exception:
        db.rollback()
        log.exception("alert evaluation failed")
