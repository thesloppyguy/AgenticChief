from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.alerts import engine as alerts_engine
from app.audit.logger import audit
from app.core.security import Principal, require_admin
from app.db.session import get_db
from app.ingestion import registry
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS
from app.services import sources_status as src_status

router = APIRouter(prefix="/ingestion")


def get_extractors(db: Session = Depends(get_db)):
    return registry.build_extractors(db=db)


def _group_wide(who: Principal) -> None:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")


@router.get("/status")
def status(db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    """Per-source health list (enriched with freshness). Prefer GET /sources/status for the full envelope."""
    _group_wide(who)
    return src_status.build_sources_list(db)


class RunRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    sources: list[str] | None = None


@router.post("/run")
def run(req: RunRequest, db: Session = Depends(get_db), who: Principal = Depends(require_admin),
        extractors=Depends(get_extractors)):
    _group_wide(who)
    unknown = set(req.sources or []) - set(SOURCE_KPIS) - {"registry"}
    if unknown:
        raise HTTPException(422, f"Unknown sources: {sorted(unknown)}")
    summaries = ingest(db, req.period, extractors, req.sources)
    alerts_engine.on_ingestion(db, summaries, req.period)
    alerts_engine.check_source_freshness(db, period=req.period)
    alerts_engine.safe_evaluate(db, req.period)
    audit(db, who, "ingestion_run", req.period, {"sources": [s.source for s in summaries]})
    db.commit()
    return [{**asdict(s), "errors": s.errors[:20]} for s in summaries]
