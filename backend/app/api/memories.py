from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.alerts import prefs as prefs_mod
from app.core.security import Principal, get_principal
from app.db.models import UserMemory
from app.db.session import get_db
from app.memory import store

router = APIRouter(prefix="/memories")


def _out(m: UserMemory) -> dict:
    return {"id": m.id, "kind": m.kind, "domain": m.domain, "summary": m.summary, "pinned": m.pinned,
            "created_at": m.created_at, "session_id": m.session_id}


@router.get("")
def list_memories(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    store.purge_expired(db, who.user_id)
    rows = db.scalars(select(UserMemory).where(UserMemory.user_id == who.user_id)
                      .order_by(UserMemory.pinned.desc(), UserMemory.id.desc()))
    return {"enabled": prefs_mod.get(db, who.user_id).memory_enabled, "memories": [_out(m) for m in rows]}


class SettingIn(BaseModel):
    enabled: bool


@router.put("/settings")
def set_enabled(body: SettingIn, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    p = prefs_mod.get(db, who.user_id)
    p.memory_enabled = body.enabled
    prefs_mod.save(db, who.user_id, p)
    return {"enabled": body.enabled}


@router.post("/{memory_id}/pin")
def toggle_pin(memory_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    m = db.get(UserMemory, memory_id)
    if m is None or m.user_id != who.user_id:  # memories are private
        raise HTTPException(404, "Memory not found")
    m.pinned = not m.pinned
    db.commit()
    return _out(m)


@router.delete("/{memory_id}", status_code=204)
def forget(memory_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    m = db.get(UserMemory, memory_id)
    if m is None or m.user_id != who.user_id:
        raise HTTPException(404, "Memory not found")
    db.delete(m)
    db.commit()


@router.delete("", status_code=204)
def forget_all(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    db.execute(delete(UserMemory).where(UserMemory.user_id == who.user_id))
    db.commit()
