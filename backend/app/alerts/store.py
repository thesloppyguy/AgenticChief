from __future__ import annotations

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.db.models import Alert, AlertRead

from . import prefs as prefs_mod


def _visible(who: Principal):
    q = select(Alert)
    if who.company_ids is not None:  # scoped users see only their companies' alerts, never group-wide ones
        q = q.where(Alert.company_id.in_(list(who.company_ids)))
    return q


def _read_by(who: Principal):
    return exists().where(AlertRead.alert_id == Alert.id, AlertRead.user_id == who.user_id)


def _wanted(db: Session, who: Principal, q):
    """Apply the user's severity and muted-kind preferences."""
    p = prefs_mod.get(db, who.user_id)
    if p.min_severity != "low":
        keep = prefs_mod.SEVERITIES[prefs_mod.SEVERITIES.index(p.min_severity):]
        q = q.where(Alert.severity.in_(keep))
    if p.muted_kinds:
        q = q.where(Alert.kind.notin_(p.muted_kinds))
    return q


def list_alerts(db: Session, who: Principal, unread_only: bool = False, limit: int = 100,
                include_hidden: bool = False) -> list[dict]:
    q = _visible(who)
    if not include_hidden:
        q = _wanted(db, who, q)
    if unread_only:
        q = q.where(~_read_by(who))
    rows = db.scalars(q.order_by(Alert.id.desc()).limit(min(limit, 500))).all()
    read_ids = set(db.scalars(select(AlertRead.alert_id).where(
        AlertRead.user_id == who.user_id, AlertRead.alert_id.in_([a.id for a in rows])))) if rows else set()
    return [{"id": a.id, "kind": a.kind, "severity": a.severity, "entity": a.entity, "company_id": a.company_id, "period": a.period,
             "title": a.title, "detail": a.detail, "created_at": a.created_at, "read": a.id in read_ids}
            for a in rows]


def unread_count(db: Session, who: Principal) -> int:
    q = _wanted(db, who, _visible(who)).where(~_read_by(who)).subquery()
    return db.scalar(select(func.count()).select_from(q)) or 0


def mark_read(db: Session, who: Principal, alert_id: int) -> bool:
    visible = db.scalar(_visible(who).where(Alert.id == alert_id))
    if visible is None:
        return False
    if not db.scalar(select(AlertRead.id).where(AlertRead.alert_id == alert_id, AlertRead.user_id == who.user_id)):
        db.add(AlertRead(alert_id=alert_id, user_id=who.user_id))
        db.commit()
    return True


def mark_all_read(db: Session, who: Principal) -> int:
    ids = db.scalars(_visible(who).where(~_read_by(who)).with_only_columns(Alert.id)).all()
    db.add_all(AlertRead(alert_id=i, user_id=who.user_id) for i in ids)
    db.commit()
    return len(ids)
