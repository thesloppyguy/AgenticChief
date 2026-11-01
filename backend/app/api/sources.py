"""Spec-shaped Sources API: status + sync. Wraps the ingestion runner; does not replace /ingestion/*."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.alerts import engine as alerts_engine
from app.api.ingestion import get_extractors
from app.audit.logger import audit
from app.core.security import Principal, require_admin
from app.db.session import get_db
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS
from app.services import sources_status as src_status

router = APIRouter(prefix="/sources", tags=["sources"])


def _group_wide(who: Principal) -> None:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")


@router.get("/status")
def status(db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    _group_wide(who)
    return src_status.build_sources_status(db)


class SyncRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def _run_sync(db: Session, who: Principal, period: str, sources: list[str] | None, extractors) -> list[dict]:
    summaries = ingest(db, period, extractors, sources)
    alerts_engine.on_ingestion(db, summaries, period)
    alerts_engine.check_source_freshness(db, period=period)
    alerts_engine.safe_evaluate(db, period)
    audit(db, who, "sources_sync", period, {"sources": [s.source for s in summaries]})
    db.commit()
    return [{**asdict(s), "errors": s.errors[:20]} for s in summaries]


@router.post("/sync")
def sync_all(req: SyncRequest, db: Session = Depends(get_db), who: Principal = Depends(require_admin),
             extractors=Depends(get_extractors)):
    _group_wide(who)
    return _run_sync(db, who, req.period, None, extractors)


@router.post("/{source}/sync")
def sync_one(source: str, req: SyncRequest, db: Session = Depends(get_db),
             who: Principal = Depends(require_admin), extractors=Depends(get_extractors)):
    _group_wide(who)
    if source not in SOURCE_KPIS:
        raise HTTPException(422, f"Unknown source: {source}")
    return _run_sync(db, who, req.period, [source], extractors)
