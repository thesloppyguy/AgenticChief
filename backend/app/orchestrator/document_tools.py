"""Executive tools for searching the document library (FTS)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.knowledge import store as doc_store

DOCUMENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_documents",
        "description": (
            "Search uploaded and built-in company documents by keyword. "
            "Use for policy, scorecard definitions, and reference material."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "domain": {
                    "type": "string",
                    "description": "Optional domain filter (hr, finance, general, …)",
                },
                "limit": {"type": "integer", "description": "Max hits (1–10)", "default": 5},
            },
            "required": ["query"],
        },
    }
]


def handle_search_documents(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"hits": [], "error": "query is required"}
    limit = int(args.get("limit") or 5)
    domain = args.get("domain") or None
    hits = doc_store.search(db, query, limit=limit, domain=domain)
    return {
        "hits": [
            {
                "document_id": h.document_id,
                "title": h.title,
                "domain": h.domain,
                "chunk": h.chunk,
                "snippet": h.snippet,
                "text": h.text[:1200],
                "score": h.score,
            }
            for h in hits
        ]
    }
