from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal
from app.dashboard import layout as layout_service
from app.db.session import get_db

router = APIRouter(prefix="/dashboard")


@router.get("/layout")
def get_dashboard_layout(
    db: Session = Depends(get_db),
    who: Principal = Depends(get_principal),
):
    return layout_service.get_layout(db, who.user_id)
