"""Always-in-the-loop history notes store and validation."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import HistoryNote, HistorySettings

KINDS = frozenset({"promised", "agreed", "declined", "answered", "asked", "shared"})
_URL_RE = re.compile(r"https?://|www\.|@", re.I)


def settings_for(db: Session, user_id: str) -> HistorySettings:
    row = db.get(HistorySettings, user_id)
    if row is None:
        row = HistorySettings(user_id=user_id, enabled=True)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def set_enabled(db: Session, user_id: str, enabled: bool) -> HistorySettings:
    row = settings_for(db, user_id)
    row.enabled = enabled
    row.updated_at = datetime.now(UTC)
    db.commit()
    return row


def check_note(summary: str, quote: str, source_text: str, kind: str) -> str | None:
    """Return an error string if the note fails safety checks, else None."""
    if kind not in KINDS:
        return "invalid kind"
    summary = (summary or "").strip()
    quote = (quote or "").strip()
    if len(summary) < 8 or len(quote) < 8:
        return "too short"
    if quote not in source_text:
        return "quote not found in source"
    if _URL_RE.search(summary):
        return "summary must not contain URLs or emails"
    # Most summary words should appear in the source.
    words = [w.lower() for w in re.findall(r"[a-zA-Z0-9']+", summary) if len(w) > 2]
    if not words:
        return "empty summary"
    src = source_text.lower()
    hits = sum(1 for w in words if w in src)
    if hits / len(words) < 0.5:
        return "summary not grounded in source"
    return None


def add_notes(
    db: Session,
    user_id: str,
    session_id: int | None,
    notes: list[dict],
    source_text: str,
) -> list[HistoryNote]:
    created: list[HistoryNote] = []
    expires = datetime.now(UTC) + timedelta(days=settings.history_retention_days)
    for raw in notes[:8]:
        kind = str(raw.get("kind") or "")
        summary = str(raw.get("summary") or "")[:400]
        quote = str(raw.get("quote") or "")[:600]
        err = check_note(summary, quote, source_text, kind)
        if err:
            continue
        due_at = None
        if kind in ("promised", "agreed") and raw.get("due_at"):
            try:
                due_at = datetime.fromisoformat(str(raw["due_at"]).replace("Z", "+00:00"))
            except ValueError:
                due_at = None
        row = HistoryNote(
            user_id=user_id,
            kind=kind,
            summary=summary,
            quote=quote,
            due_at=due_at,
            session_id=session_id,
            expires_at=expires,
        )
        db.add(row)
        created.append(row)
    if created:
        db.commit()
        for r in created:
            db.refresh(r)
    return created


def list_notes(db: Session, user_id: str, *, include_expired: bool = False) -> list[HistoryNote]:
    now = datetime.now(UTC)
    q = select(HistoryNote).where(HistoryNote.user_id == user_id)
    if not include_expired:
        q = q.where(
            or_(HistoryNote.expires_at.is_(None), HistoryNote.expires_at > now, HistoryNote.pinned)
        )
    return list(
        db.scalars(q.order_by(HistoryNote.pinned.desc(), HistoryNote.id.desc()).limit(200))
    )


def due_soon(db: Session, user_id: str, *, within_days: int = 2) -> list[HistoryNote]:
    now = datetime.now(UTC)
    until = now + timedelta(days=within_days)
    return list(
        db.scalars(
            select(HistoryNote)
            .where(
                HistoryNote.user_id == user_id,
                HistoryNote.due_at.is_not(None),
                HistoryNote.due_at >= now,
                HistoryNote.due_at <= until,
            )
            .order_by(HistoryNote.due_at)
            .limit(20)
        )
    )


def render_block(notes: list[HistoryNote]) -> str:
    if not notes:
        return ""
    lines = ["<history_notes>"]
    for n in notes:
        due = f" due={n.due_at.date().isoformat()}" if n.due_at else ""
        corr = f" (corrected: {n.correction})" if n.correction else ""
        lines.append(f"- [{n.kind}{due}] {n.correction or n.summary}{corr}")
    lines.append("</history_notes>")
    return "\n".join(lines)
