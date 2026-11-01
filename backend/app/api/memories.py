from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.alerts import prefs as prefs_mod
from app.core.security import Principal, get_principal
from app.db.models import HistoryNote, UserMemory
from app.db.session import get_db
from app.memory import history_notes, store

router = APIRouter(prefix="/memories")


def _out(m: UserMemory) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "domain": m.domain,
        "summary": m.summary,
        "pinned": m.pinned,
        "created_at": m.created_at,
        "session_id": m.session_id,
    }


def _history_out(n: HistoryNote) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "summary": n.summary,
        "quote": n.quote,
        "due_at": n.due_at,
        "pinned": n.pinned,
        "correction": n.correction,
        "created_at": n.created_at,
        "session_id": n.session_id,
    }


@router.get("")
def list_memories(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    store.purge_expired(db, who.user_id)
    rows = db.scalars(
        select(UserMemory)
        .where(UserMemory.user_id == who.user_id)
        .order_by(UserMemory.pinned.desc(), UserMemory.id.desc())
    )
    return {
        "enabled": prefs_mod.get(db, who.user_id).memory_enabled,
        "memories": [_out(m) for m in rows],
    }


class SettingIn(BaseModel):
    enabled: bool


@router.put("/settings")
def set_enabled(
    body: SettingIn, db: Session = Depends(get_db), who: Principal = Depends(get_principal)
):
    p = prefs_mod.get(db, who.user_id)
    p.memory_enabled = body.enabled
    prefs_mod.save(db, who.user_id, p)
    return {"enabled": body.enabled}


@router.get("/history")
def list_history(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    enabled = history_notes.settings_for(db, who.user_id).enabled
    notes = history_notes.list_notes(db, who.user_id)
    return {"enabled": enabled, "notes": [_history_out(n) for n in notes]}


class HistorySettingIn(BaseModel):
    enabled: bool


@router.put("/history/settings")
def set_history_enabled(
    body: HistorySettingIn,
    db: Session = Depends(get_db),
    who: Principal = Depends(get_principal),
):
    row = history_notes.set_enabled(db, who.user_id, body.enabled)
    return {"enabled": row.enabled}


class HistoryPatch(BaseModel):
    pinned: bool | None = None
    correction: str | None = Field(default=None, max_length=400)


@router.patch("/history/{note_id}")
def patch_history(
    note_id: int,
    body: HistoryPatch,
    db: Session = Depends(get_db),
    who: Principal = Depends(get_principal),
):
    n = db.get(HistoryNote, note_id)
    if n is None or n.user_id != who.user_id:
        raise HTTPException(404, "Note not found")
    if body.pinned is not None:
        n.pinned = body.pinned
    if body.correction is not None:
        n.correction = body.correction.strip() or None
    db.commit()
    db.refresh(n)
    return _history_out(n)


@router.delete("/history/{note_id}", status_code=204)
def forget_history(
    note_id: int,
    db: Session = Depends(get_db),
    who: Principal = Depends(get_principal),
):
    n = db.get(HistoryNote, note_id)
    if n is None or n.user_id != who.user_id:
        raise HTTPException(404, "Note not found")
    db.delete(n)
    db.commit()


@router.post("/{memory_id}/pin")
def toggle_pin(
    memory_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)
):
    m = db.get(UserMemory, memory_id)
    if m is None or m.user_id != who.user_id:
        raise HTTPException(404, "Memory not found")
    m.pinned = not m.pinned
    db.commit()
    return _out(m)


@router.delete("/{memory_id}", status_code=204)
def forget(
    memory_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)
):
    m = db.get(UserMemory, memory_id)
    if m is None or m.user_id != who.user_id:
        raise HTTPException(404, "Memory not found")
    db.delete(m)
    db.commit()


@router.delete("", status_code=204)
def forget_all(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    db.execute(delete(UserMemory).where(UserMemory.user_id == who.user_id))
    db.commit()
