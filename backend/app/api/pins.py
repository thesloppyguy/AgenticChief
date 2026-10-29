from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal
from app.db.models import Asset, ChatSession, Pin, ReportSnapshot, WorkflowRun
from app.db.session import get_db

router = APIRouter(prefix="/pins")
KINDS = ("run", "snapshot", "session", "skill", "agent", "view")
_VIEW = re.compile(r"^/[A-Za-z0-9/_\-?=&%.,:+]{0,280}$")


def _href(kind: str, ref: str) -> str:
    return {"run": f"/reports/runs/{ref}", "snapshot": f"/reports/snapshots/{ref}", "session": f"/copilot?session={ref}",
            "skill": f"/skills/{ref}", "agent": f"/agents/{ref}", "view": ref}[kind]


def _validate(db: Session, who: Principal, kind: str, ref: str) -> str:
    """Return a default label, or raise. You can only pin something you are allowed to open."""
    group_wide = who.company_ids is None
    if kind in ("run", "snapshot"):
        if not group_wide:
            raise HTTPException(403, "Reports need group-wide access")
        row = db.get(WorkflowRun if kind == "run" else ReportSnapshot, int(ref)) if ref.isdigit() else None
        if row is None:
            raise HTTPException(404, "Nothing to pin there")
        return f"Monthly review {row.period}" if kind == "run" else f"Published {row.kind.replace('_', ' ')} {row.period}"
    if kind == "session":
        s = db.get(ChatSession, int(ref)) if ref.isdigit() else None
        if s is None or s.user_id != who.user_id:  # sessions are private
            raise HTTPException(404, "Nothing to pin there")
        return s.title
    if kind in ("skill", "agent"):
        a = db.scalar(select(Asset).where(Asset.kind == kind, Asset.key == ref))
        if a is None:
            raise HTTPException(404, "Nothing to pin there")
        return a.name
    if kind == "view":
        if not _VIEW.match(ref) or ref.startswith("//"):  # an in-app path only: never a link to another site
            raise HTTPException(422, "A view must be an in-app path such as /?period=2026-10&status=red")
        return "Dashboard view"
    raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")


def _out(p: Pin) -> dict:
    return {"id": p.id, "kind": p.kind, "ref": p.ref, "label": p.label, "href": _href(p.kind, p.ref),
            "created_at": p.created_at}


class PinIn(BaseModel):
    kind: str
    ref: str = Field(min_length=1, max_length=300)
    label: str | None = Field(default=None, max_length=200)


@router.get("")
def list_pins(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    rows = db.scalars(select(Pin).where(Pin.user_id == who.user_id).order_by(Pin.id.desc()))
    return [_out(p) for p in rows]


@router.post("", status_code=201)
def pin(body: PinIn, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    default = _validate(db, who, body.kind, body.ref)
    existing = db.scalar(select(Pin).where(Pin.user_id == who.user_id, Pin.kind == body.kind, Pin.ref == body.ref))
    if existing:  # pinning twice is not an error
        return _out(existing)
    p = Pin(user_id=who.user_id, kind=body.kind, ref=body.ref, label=(body.label or default)[:200])
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        p = db.scalar(select(Pin).where(Pin.user_id == who.user_id, Pin.kind == body.kind, Pin.ref == body.ref))
    return _out(p)


@router.delete("/{pin_id}", status_code=204)
def unpin(pin_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    p = db.get(Pin, pin_id)
    if p is None or p.user_id != who.user_id:
        raise HTTPException(404, "Pin not found")
    db.delete(p)
    db.commit()
