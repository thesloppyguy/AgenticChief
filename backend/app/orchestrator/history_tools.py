"""Executive tool to recall the caller's private history notes."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.security import Principal
from app.memory import history_notes

HISTORY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "recall_history",
        "description": (
            "Recall this person's private always-in-the-loop notes "
            "(promises, agreements, asks). Only their own notes are returned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional filter text; leave blank for recent notes",
                },
                "limit": {"type": "integer", "default": 12},
            },
        },
    }
]


def handle_recall_history(
    db: Session, who: Principal, args: dict[str, Any]
) -> dict[str, Any]:
    notes = history_notes.list_notes(db, who.user_id)
    q = str(args.get("query") or "").strip().lower()
    if q:
        notes = [
            n
            for n in notes
            if q in (n.summary or "").lower()
            or q in (n.quote or "").lower()
            or q in (n.correction or "").lower()
        ]
    limit = max(1, min(int(args.get("limit") or 12), 30))
    notes = notes[:limit]
    return {
        "notes": [
            {
                "id": n.id,
                "kind": n.kind,
                "summary": n.correction or n.summary,
                "quote": n.quote,
                "due_at": n.due_at.isoformat() if n.due_at else None,
                "pinned": n.pinned,
            }
            for n in notes
        ],
        "block": history_notes.render_block(notes),
    }
