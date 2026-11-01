"""Seed builtin Markdown knowledge into Chroma and mirror company docs."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.chroma_store import ChromaDBStore
from app.knowledge.chunking import chunk_text

logger = logging.getLogger(__name__)

DOCS_ROOT = Path(__file__).resolve().parent / "docs"


def _chunk_id(source: str, index: int) -> str:
    return hashlib.md5(f"{source}::chunk::{index}".encode()).hexdigest()


def _domain_from_path(path: Path) -> str:
    # docs/<domain>/file.md → domain
    try:
        rel = path.relative_to(DOCS_ROOT)
        if rel.parts:
            return rel.parts[0]
    except ValueError:
        pass
    return "general"


def seed_builtin_knowledge(force: bool = False) -> int:
    """Index shipped Markdown under knowledge/docs into builtin_knowledge."""
    if not DOCS_ROOT.is_dir():
        return 0
    store = ChromaDBStore(settings.vector_store_path)
    existing = {
        meta.get("source")
        for _, meta in store.iter_chunk_metadata(ChromaDBStore.BUILTIN_COLLECTION)
        if meta.get("source")
    }
    texts: list[str] = []
    metas: list[dict] = []
    ids: list[str] = []
    files = sorted(DOCS_ROOT.rglob("*.md"))
    for path in files:
        source = str(path.relative_to(DOCS_ROOT))
        if not force and source in existing:
            continue
        body = path.read_text(encoding="utf-8")
        chunks = chunk_text(body)
        domain = _domain_from_path(path)
        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            metas.append(
                {
                    "domain": domain,
                    "filename": path.name,
                    "source": source,
                    "chunk_index": i,
                    "type": "builtin",
                }
            )
            ids.append(_chunk_id(source, i))
    if texts:
        store.add_documents(texts, metas, ids, ChromaDBStore.BUILTIN_COLLECTION)
    logger.info("seeded %d builtin knowledge chunk(s) from %d file(s)", len(texts), len(files))
    return len(texts)


def mirror_document_chunks(
    *,
    document_id: int,
    title: str,
    domain: str,
    chunks: list[str],
    builtin: bool = False,
) -> None:
    """Upsert a document's chunks into the company_docs (or builtin) collection."""
    store = ChromaDBStore(settings.vector_store_path)
    collection = (
        ChromaDBStore.BUILTIN_COLLECTION if builtin else ChromaDBStore.COMPANY_COLLECTION
    )
    # Replace prior chunks for this document
    store.delete_documents(collection, {"document_id": document_id})
    if not chunks:
        return
    texts, metas, ids = [], [], []
    for i, chunk in enumerate(chunks):
        texts.append(chunk)
        metas.append(
            {
                "domain": domain or "general",
                "filename": title,
                "title": title,
                "document_id": document_id,
                "chunk_index": i,
                "type": "builtin" if builtin else "company",
            }
        )
        ids.append(_chunk_id(f"doc:{document_id}", i))
    store.add_documents(texts, metas, ids, collection)


def remirror_all_company_docs(db: Session) -> int:
    """Best-effort: push all SQL documents into Chroma company/builtin collections."""
    from sqlalchemy import select

    from app.db.models import Document, DocumentChunk

    docs = list(db.scalars(select(Document)))
    n = 0
    for doc in docs:
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == doc.id)
                .order_by(DocumentChunk.ord)
            )
        )
        mirror_document_chunks(
            document_id=doc.id,
            title=doc.title,
            domain=doc.domain,
            chunks=[c.text for c in chunks],
            builtin=bool(doc.builtin),
        )
        n += 1
    return n
