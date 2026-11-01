"""Admin fixture load API (L&T Group CHRO demo)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import Principal, require_admin
from app.db.session import get_db
from app.fixtures.lnt_loader import load_lnt
from app.fixtures.paths import COMPANIES_DIR, GROUP_DIR, SEED_ROOT
from app.org.companies import FIXTURE_SLUGS, LNT_COMPANIES
from app.services.scorecard import current_period

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


@router.get("")
def list_fixtures(_: Principal = Depends(require_admin)):
    return {
        "seed_root": str(SEED_ROOT),
        "group": str(GROUP_DIR) if GROUP_DIR.exists() else None,
        "companies": [
            {
                "code": code,
                "name": name,
                "archetype": arch,
                "slug": FIXTURE_SLUGS[code],
                "path": str(COMPANIES_DIR / FIXTURE_SLUGS[code]),
            }
            for code, name, arch in LNT_COMPANIES
        ],
    }


class LoadIn(BaseModel):
    reset: bool = True
    ingest: bool = True
    through: str | None = Field(default=None, description="YYYY-MM; defaults to current period")


@router.post("/lnt/load")
def load_lnt_fixture(
    body: LoadIn | None = None,
    db: Session = Depends(get_db),
    who: Principal = Depends(require_admin),
):
    body = body or LoadIn()
    summary = load_lnt(
        db=db,
        reset=body.reset,
        ingest=body.ingest,
        through=body.through or current_period(),
        user_id=who.user_id,
    )
    return {"ok": True, "summary": summary}
