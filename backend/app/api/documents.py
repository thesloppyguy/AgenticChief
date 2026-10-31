from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal, require_editor
from app.db.models import Document, DocumentChunk
from app.db.session import get_db
from app.knowledge import store
from app.knowledge.parsers import MAX_BYTES, ParseError, UnsupportedType

router = APIRouter(prefix="/documents")


def _out(d: Document) -> dict:
    return {"id": d.id, "title": d.title, "filename": d.filename, "domain": d.domain, "builtin": d.builtin,
            "size_bytes": d.size_bytes, "chunk_count": d.chunk_count, "uploaded_by": d.uploaded_by,
            "created_at": d.created_at}


@router.get("")
def list_documents(db: Session = Depends(get_db), _: Principal = Depends(get_principal)):
    return [_out(d) for d in db.scalars(select(Document).order_by(Document.builtin.desc(), Document.id.desc()))]


@router.get("/search")
def search(q: str, domain: str | None = None, limit: int = 5, db: Session = Depends(get_db),
           _: Principal = Depends(get_principal)):
    if domain is not None and domain not in store.DOMAINS:
        raise HTTPException(422, f"domain must be one of {', '.join(store.DOMAINS)}")
    return [{"document_id": h.document_id, "title": h.title, "domain": h.domain, "chunk": h.chunk,
             "snippet": h.snippet, "score": round(h.score, 3)} for h in store.search(db, q, limit, domain)]


@router.get("/{doc_id}")
def read(doc_id: int, db: Session = Depends(get_db), _: Principal = Depends(get_principal)):
    """The indexed text, rebuilt from its passages (overlapping words between windows are dropped once)."""
    d = db.get(Document, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    passages = db.scalars(select(DocumentChunk.text).where(DocumentChunk.document_id == doc_id)
                          .order_by(DocumentChunk.ord)).all()
    out: list[str] = []
    for p in passages:
        if out:
            prev, words = out[-1].split(" "), p.split(" ")
            n = next((k for k in range(min(len(prev), len(words), 60), 0, -1) if prev[-k:] == words[:k]), 0)
            p = " ".join(words[n:])
        out.append(p)
    return {**_out(d), "text": "\n\n".join(out)}


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), title: str = Form(""), domain: str = Form("general"),
                 db: Session = Depends(get_db), who: Principal = Depends(require_editor)):
    if domain not in store.DOMAINS:
        raise HTTPException(422, f"domain must be one of {', '.join(store.DOMAINS)}")
    data = await file.read(MAX_BYTES + 1)  # never read more than the limit allows
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"Files over {MAX_BYTES // 1_000_000} MB are not accepted")
    name = (file.filename or "upload").replace("\\", "/").split("/")[-1]
    try:
        doc = store.add_document(db, who, title or name, name, data, domain)
    except UnsupportedType as e:
        raise HTTPException(415, str(e)) from e
    except ParseError as e:
        raise HTTPException(422, str(e)) from e
    except store.DuplicateDocument as e:
        raise HTTPException(409, f"{e} (document #{e.existing_id})") from e
    return _out(doc)


@router.delete("/{doc_id}", status_code=204)
def delete(doc_id: int, db: Session = Depends(get_db), who: Principal = Depends(require_editor)):
    d = db.get(Document, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    if d.builtin:
        raise HTTPException(403, "Built-in documents cannot be deleted")
    store.delete_document(db, who, d)
