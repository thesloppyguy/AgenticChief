"""Domain-aware RAG over builtin + company Chroma collections."""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.knowledge.chroma_store import ChromaDBStore

logger = logging.getLogger(__name__)

_DISTANCE_THRESHOLD = 0.55
_MIN_QUERY_CHARS = 3

DOMAIN_ALIASES: dict[str, list[str]] = {
    "cso": ["strategy"],
    "cfo": ["finance"],
    "chro": ["hr"],
    "gc": ["legal"],
    "coo": ["operations"],
    "cmo": ["marketing"],
    "cpo": ["product", "strategy"],
    "sales": ["sales", "marketing"],
    "board_comms": ["board", "finance"],
    "triage": ["general", "operations"],
}


def _store() -> ChromaDBStore:
    return ChromaDBStore(settings.vector_store_path)


def _passes(row: dict[str, Any], threshold: float = _DISTANCE_THRESHOLD) -> bool:
    distance = row.get("distance")
    if distance is None:
        return False
    return float(distance) <= threshold


def _dedupe(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in results:
        text = r.get("text") or ""
        if text in seen:
            continue
        seen.add(text)
        out.append(r)
    return out


def _format(rows: list[dict[str, Any]], label: str) -> str:
    if not rows:
        return ""
    parts = [f"### {label}"]
    for r in rows:
        meta = r.get("metadata") or {}
        src = meta.get("filename") or meta.get("title") or meta.get("source") or "source"
        domain = meta.get("domain") or ""
        header = f"[{src}" + (f" · {domain}" if domain else "") + "]"
        parts.append(f"{header}\n{(r.get('text') or '').strip()}")
    return "\n\n".join(parts)


def retrieve(
    query: str,
    *,
    specialist_name: str | None = None,
    n_builtin: int = 4,
    n_company: int = 4,
    store: ChromaDBStore | None = None,
) -> str:
    """Return a Markdown block of relevant knowledge, or empty string."""
    q = (query or "").strip()
    if len(q) < _MIN_QUERY_CHARS:
        return ""
    chroma = store or _store()
    domains = DOMAIN_ALIASES.get(specialist_name or "", None)
    # Company docs: always include "general" so unclassified uploads are visible.
    company_domains = list({*(domains or []), "general"}) if domains else None

    builtin: list[dict[str, Any]] = []
    company: list[dict[str, Any]] = []
    try:
        if n_builtin > 0:
            where = {"domain": {"$in": domains}} if domains else None
            rows = chroma.query(
                q,
                ChromaDBStore.BUILTIN_COLLECTION,
                n_results=n_builtin * 2,
                where=where,
            )
            builtin = [r for r in rows if _passes(r)][:n_builtin]
        if n_company > 0:
            where = {"domain": {"$in": company_domains}} if company_domains else None
            rows = chroma.query(
                q,
                ChromaDBStore.COMPANY_COLLECTION,
                n_results=n_company * 2,
                where=where,
            )
            company = [r for r in rows if _passes(r)][:n_company]
    except Exception:
        logger.exception("retrieve failed for specialist=%s", specialist_name)
        return ""

    builtin = _dedupe(builtin)
    company = _dedupe(company)
    blocks = [
        b
        for b in (
            _format(company, "Company documents"),
            _format(builtin, "Built-in knowledge"),
        )
        if b
    ]
    return "\n\n".join(blocks)
