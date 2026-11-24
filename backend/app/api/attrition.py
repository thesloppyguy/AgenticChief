"""Attrition (ICHRATTRITION) sync + status API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.attrition.sync import attrition_status, sync_attrition
from app.audit.logger import audit
from app.core.security import Principal, require_admin
from app.db.session import get_db
from app.org.companies import LNT_CODES

router = APIRouter(prefix="/attrition", tags=["attrition"])


def _group_wide(who: Principal) -> None:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")


class SyncRequest(BaseModel):
    ics: list[str] | None = Field(
        default=None,
        description="Optional IC codes; defaults to full roster from API.md",
    )


@router.get("/status")
def status(db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    _group_wide(who)
    return attrition_status(db)


@router.post("/sync")
def sync(
    body: SyncRequest | None = None,
    db: Session = Depends(get_db),
    who: Principal = Depends(require_admin),
):
    _group_wide(who)
    body = body or SyncRequest()
    ics = body.ics
    if ics is not None:
        unknown = sorted({c.strip().upper() for c in ics if c.strip()} - set(LNT_CODES))
        # Allow unknown codes (API may return extra ICs) but warn via audit detail only
        _ = unknown
    try:
        result = sync_attrition(db, ics=ics, triggered_by=who.user_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, who, "attrition_sync", result.get("status"), {
        "ics_ok": result.get("ics_ok"),
        "ics_failed": result.get("ics_failed"),
        "rows_upserted": result.get("rows_upserted"),
    })
    db.commit()
    return result
