"""Documents, chunks and SQLite FTS5 search (BM25 ranking)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import delete, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.core.security import Principal
from app.db.models import Document, DocumentChunk

from .chunking import chunk_text
from .parsers import extract_text

DOMAINS = ("general", "hr", "legal", "policy", "finance", "operations", "scorecard")
_STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "is", "are", "for", "on", "what", "how", "do", "does", "we"}
FTS_DDL = "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text, chunk_id UNINDEXED, document_id UNINDEXED)"


class DuplicateDocument(ValueError):
    def __init__(self, existing_id: int):
        super().__init__("that document has already been uploaded")
        self.existing_id = existing_id


@dataclass
class Hit:
    document_id: int
    title: str
    domain: str
    chunk: int
    snippet: str
    text: str
    score: float


def ensure_fts(bind: Engine | Connection) -> None:
    """The FTS table is created by migration 0006; tests that build the schema from the models call this."""
    if isinstance(bind, Engine):
        with bind.begin() as conn:
            conn.execute(text(FTS_DDL))
    else:
        bind.execute(text(FTS_DDL))


def fts_query(q: str) -> str | None:
    """Turn free text into a safe FTS5 expression. Every token is quoted, so FTS operators and punctuation
    in user input (quotes, NEAR, *, -, parentheses) can never be a syntax error or a query trick."""
    # Single letters are noise; single digits are not ("CPR 7").
    tokens = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if t not in _STOP and (len(t) > 1 or t.isdigit())][:12]
    if not tokens:
        return None
    return " OR ".join(f'"{t}"*' if len(t) >= 3 else f'"{t}"' for t in tokens)


def add_document(db: Session, who: Principal, title: str, filename: str, data: bytes, domain: str = "general",
                 builtin: bool = False, commit: bool = True) -> Document:
    """`commit=False` leaves the work in the caller's transaction (used inside approval executors)."""
    body = extract_text(filename, data)
    digest = hashlib.sha256(body.encode()).hexdigest()
    dup = db.scalar(select(Document.id).where(Document.content_hash == digest))
    if dup:
        raise DuplicateDocument(dup)
    chunks = chunk_text(body)
    doc = Document(title=title.strip()[:200] or filename, filename=filename[:255], domain=domain, builtin=builtin,
                   content_hash=digest, size_bytes=len(data), chunk_count=len(chunks), uploaded_by=who.user_id)
    db.add(doc)
    db.flush()
    for i, c in enumerate(chunks):
        row = DocumentChunk(document_id=doc.id, ord=i, text=c)
        db.add(row)
        db.flush()
        db.execute(text("INSERT INTO chunk_fts(text, chunk_id, document_id) VALUES (:t, :c, :d)"),
                   # The title is indexed with every passage so a search by a document's name finds it.
                   {"t": f"{doc.title}\n{c}", "c": row.id, "d": doc.id})
    try:
        from app.knowledge.loader import mirror_document_chunks

        mirror_document_chunks(
            document_id=doc.id,
            title=doc.title,
            domain=domain,
            chunks=chunks,
            builtin=builtin,
        )
    except Exception:
        pass
    audit(db, who, "document_added", f"{doc.id}:{doc.title}", {"chunks": len(chunks), "builtin": builtin})
    if commit:
        db.commit()
    return doc


def delete_document(db: Session, who: Principal, doc: Document, commit: bool = True) -> None:
    db.execute(text("DELETE FROM chunk_fts WHERE document_id = :d"), {"d": doc.id})
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    try:
        from app.knowledge.chroma_store import ChromaDBStore
        from app.core.config import settings

        store = ChromaDBStore(settings.vector_store_path)
        coll = (
            ChromaDBStore.BUILTIN_COLLECTION
            if doc.builtin
            else ChromaDBStore.COMPANY_COLLECTION
        )
        store.delete_documents(coll, {"document_id": doc.id})
    except Exception:
        pass
    audit(db, who, "document_deleted", f"{doc.id}:{doc.title}")
    db.delete(doc)
    if commit:
        db.commit()
    else:
        db.flush()


def search(db: Session, query: str, limit: int = 5, domain: str | None = None) -> list[Hit]:
    expr = fts_query(query)
    if expr is None:
        return []
    sql = ("SELECT f.chunk_id, f.document_id, snippet(chunk_fts, 0, '[', ']', ' … ', 24) AS snip, bm25(chunk_fts) AS rank "
           "FROM chunk_fts f JOIN document d ON d.id = f.document_id "
           "WHERE chunk_fts MATCH :q" + (" AND d.domain = :dom" if domain else "") +
           " ORDER BY rank LIMIT :n")
    params: dict = {"q": expr, "n": max(1, min(limit, 20))}
    if domain:
        params["dom"] = domain
    hits = []
    for chunk_id, doc_id, snip, rank in db.execute(text(sql), params):
        chunk = db.get(DocumentChunk, chunk_id)
        doc = db.get(Document, doc_id)
        if chunk and doc:
            hits.append(Hit(doc.id, doc.title, doc.domain, chunk.ord, snip, chunk.text, -float(rank)))
    return hits
