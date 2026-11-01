"""remind_me and open-loop Executive tools."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import Principal
from app.db.models import Reminder
from app.memory import open_loops

_LINK_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+")

REMINDER_TOOLS: list[dict[str, Any]] = [
    {
        "name": "remind_me",
        "description": (
            "Schedule a private fixed-text reminder for the current user. "
            "Delivered in-app when due. No links or email addresses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind them of"},
                "run_at": {
                    "type": "string",
                    "description": "ISO8601 UTC datetime when the reminder is due",
                },
            },
            "required": ["text", "run_at"],
        },
    },
    {
        "name": "list_open_loops",
        "description": "List this user's open commitments / open loops.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "assign_open_loop",
        "description": (
            "Track an open loop. The description (or quote) must appear in the "
            "user's current message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "quote": {"type": "string"},
                "due_at": {"type": "string"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "close_open_loop",
        "description": "Close an open loop by id.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
]


def _sanitize(text: str) -> str:
    return _LINK_RE.sub("[redacted]", text).strip()[:400]


def handle(
    db: Session,
    who: Principal,
    name: str,
    args: dict[str, Any],
    *,
    session_id: int | None = None,
    user_message: str = "",
) -> Any:
    if name == "remind_me":
        text = _sanitize(str(args.get("text") or ""))
        if len(text) < 3:
            return {"error": "text too short"}
        try:
            due = datetime.fromisoformat(str(args.get("run_at")).replace("Z", "+00:00"))
        except Exception:
            return {"error": "run_at must be ISO8601"}
        if due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if due <= now:
            return {"error": "run_at must be in the future"}
        if due > now + timedelta(days=365):
            return {"error": "run_at too far in the future"}
        pending = db.scalar(
            select(func.count())
            .select_from(Reminder)
            .where(
                Reminder.user_id == who.user_id,
                Reminder.sent_at.is_(None),
                Reminder.cancelled_at.is_(None),
            )
        ) or 0
        if pending >= settings.reminder_max_pending:
            return {"error": "too many pending reminders"}
        row = Reminder(
            user_id=who.user_id,
            text=text,
            due_at=due,
            session_id=session_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "due_at": row.due_at.isoformat(), "text": row.text}

    if name == "list_open_loops":
        loops = open_loops.list_open(db, who.user_id)
        return {
            "loops": [
                {
                    "id": L.id,
                    "description": L.description,
                    "due_at": L.due_at.isoformat() if L.due_at else None,
                    "status": L.status,
                }
                for L in loops
            ]
        }

    if name == "assign_open_loop":
        desc = str(args.get("description") or "").strip()[:400]
        quote = str(args.get("quote") or "").strip()
        # Prefer verifying against quote; fall back to description in message when provided.
        if user_message and quote and quote not in user_message:
            return {"error": "quote must appear in the user's message"}
        due_at = None
        if args.get("due_at"):
            try:
                due_at = datetime.fromisoformat(str(args["due_at"]).replace("Z", "+00:00"))
            except ValueError:
                return {"error": "invalid due_at"}
        row = open_loops.assign(
            db, who.user_id, desc, quote=quote, due_at=due_at, session_id=session_id
        )
        return {"id": row.id, "description": row.description, "status": row.status}

    if name == "close_open_loop":
        row = open_loops.close(db, who.user_id, int(args.get("id") or 0))
        if row is None:
            return {"error": "open loop not found"}
        return {"id": row.id, "status": row.status}

    return {"error": f"unknown tool {name}"}
