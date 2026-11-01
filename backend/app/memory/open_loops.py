"""Open-loop tracking and post-chat extraction."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import OpenLoop

logger = logging.getLogger(__name__)

_KEYWORDS = re.compile(
    r"\b(follow up|remind|due|by friday|next week|i'll|i will|we need to|todo|to-do|action)\b",
    re.I,
)

_EXTRACT_SYSTEM = """Extract open loops (outstanding commitments) from the conversation.
Return ONLY a JSON array of {"description","quote","due_at"?,"close"?:bool}.
quote MUST be an exact substring of the USER message.
close=true means the user said the item is done.
If none, return []."""


def _scope_key(user_id: str, description: str) -> str:
    digest = hashlib.sha256(f"{user_id}:{description.strip().lower()}".encode()).hexdigest()
    return digest[:40]


def list_open(db: Session, user_id: str) -> list[OpenLoop]:
    return list(
        db.scalars(
            select(OpenLoop)
            .where(OpenLoop.user_id == user_id, OpenLoop.status == "open")
            .order_by(OpenLoop.id.desc())
            .limit(50)
        )
    )


def assign(
    db: Session,
    user_id: str,
    description: str,
    *,
    quote: str = "",
    due_at: datetime | None = None,
    session_id: int | None = None,
) -> OpenLoop:
    key = _scope_key(user_id, description)
    existing = db.scalar(
        select(OpenLoop).where(
            OpenLoop.user_id == user_id, OpenLoop.scope_key == key, OpenLoop.status == "open"
        )
    )
    if existing:
        return existing
    row = OpenLoop(
        user_id=user_id,
        description=description[:400],
        quote=(quote or "")[:600],
        due_at=due_at,
        scope_key=key,
        session_id=session_id,
        status="open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def close(db: Session, user_id: str, loop_id: int) -> OpenLoop | None:
    row = db.get(OpenLoop, loop_id)
    if row is None or row.user_id != user_id:
        return None
    row.status = "closed"
    row.closed_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


async def schedule_open_loop_pass(
    factory: sessionmaker,
    client: Any,
    user_id: str,
    session_id: int | None,
    user_message: str,
    assistant_text: str,
) -> None:
    if len(user_message) < 40 or not _KEYWORDS.search(user_message):
        return
    try:
        resp = await client.messages.create(
            model=settings.routing_model,
            max_tokens=700,
            system=_EXTRACT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User:\n{user_message[:4000]}\n\nAssistant:\n{assistant_text[:2000]}"
                    ),
                }
            ],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end < 0:
            return
        items = json.loads(text[start : end + 1])
        if not isinstance(items, list):
            return
        with factory() as db:
            for raw in items[:5]:
                quote = str(raw.get("quote") or "")
                desc = str(raw.get("description") or "")[:400]
                if not desc or (quote and quote not in user_message):
                    continue
                if raw.get("close"):
                    for loop in list_open(db, user_id):
                        if desc.lower() in loop.description.lower():
                            close(db, user_id, loop.id)
                    continue
                due_at = None
                if raw.get("due_at"):
                    try:
                        due_at = datetime.fromisoformat(
                            str(raw["due_at"]).replace("Z", "+00:00")
                        )
                    except ValueError:
                        due_at = None
                assign(
                    db,
                    user_id,
                    desc,
                    quote=quote,
                    due_at=due_at,
                    session_id=session_id,
                )
    except Exception:
        logger.exception("open loop extraction failed")
