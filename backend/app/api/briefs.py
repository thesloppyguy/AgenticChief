"""In-app morning brief / EOD digest artifacts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal
from app.db.models import BriefArtifact
from app.db.session import get_db

router = APIRouter(prefix="/briefs", tags=["briefs"])


@router.get("/latest")
def latest(
    kind: str | None = None,
    db: Session = Depends(get_db),
    _who: Principal = Depends(get_principal),
) -> dict:
    q = select(BriefArtifact).order_by(BriefArtifact.id.desc()).limit(1)
    if kind:
        if kind not in ("morning_brief", "end_of_day_digest"):
            raise HTTPException(422, "kind must be morning_brief or end_of_day_digest")
        q = (
            select(BriefArtifact)
            .where(BriefArtifact.kind == kind)
            .order_by(BriefArtifact.id.desc())
            .limit(1)
        )
    row = db.scalar(q)
    if row is None:
        return {"brief": None}
    return {
        "brief": {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "body": row.body,
            "period_date": row.period_date,
            "created_at": row.created_at,
        }
    }


@router.get("")
def list_briefs(
    limit: int = 10,
    db: Session = Depends(get_db),
    _who: Principal = Depends(get_principal),
) -> dict:
    rows = list(
        db.scalars(select(BriefArtifact).order_by(BriefArtifact.id.desc()).limit(max(1, min(limit, 50))))
    )
    return {
        "briefs": [
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "period_date": r.period_date,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.get("/{brief_id}")
def get_brief(
    brief_id: int,
    db: Session = Depends(get_db),
    _who: Principal = Depends(get_principal),
) -> dict:
    row = db.get(BriefArtifact, brief_id)
    if row is None:
        raise HTTPException(404, "brief not found")
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "period_date": row.period_date,
        "created_at": row.created_at,
    }
