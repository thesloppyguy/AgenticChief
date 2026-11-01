"""Background extraction of always-in-the-loop notes from chat turns."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.memory import history_notes

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """You extract private dated notes from what the USER said in a chat.
Return ONLY a JSON array of objects: {"kind","summary","quote","due_at"?}.
kind is one of: promised, agreed, declined, answered, asked, shared.
quote MUST be an exact substring of the user's message.
summary must be grounded in the quote — no new names, dates, figures, URLs, or emails.
due_at (ISO8601 UTC) only for promised/agreed when a date is explicit.
If nothing noteworthy, return []."""


async def schedule_chat_notes(
    factory: sessionmaker,
    client: Any,
    user_id: str,
    session_id: int | None,
    user_message: str,
    assistant_text: str,
) -> None:
    del assistant_text  # notes are grounded in the user's words only
    if len(user_message.strip()) < 40:
        return
    with factory() as db:
        if not history_notes.settings_for(db, user_id).enabled:
            return
    try:
        resp = await client.messages.create(
            model=settings.routing_model,
            max_tokens=800,
            system=_EXTRACT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"User message:\n{user_message[:6000]}",
                }
            ],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end < 0:
            return
        notes = json.loads(text[start : end + 1])
        if not isinstance(notes, list) or not notes:
            return
        with factory() as db:
            history_notes.add_notes(db, user_id, session_id, notes, user_message)
    except Exception:
        logger.exception("history note extraction failed")
