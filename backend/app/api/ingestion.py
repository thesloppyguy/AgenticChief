from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import engine as alerts_engine
from app.audit.logger import audit
from app.core.security import Principal, require_admin
from app.db.models import IngestionRun, KpiRecord
from app.db.session import get_db
from app.ingestion import registry
from app.ingestion.runner import ingest
from app.ingestion.sources import SOURCE_KPIS

router = APIRouter(prefix="/ingestion")


def get_extractors(db: Session = Depends(get_db)):
    return registry.build_extractors(db=db)


def _group_wide(who: Principal) -> None:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")


@router.get("/status")
def status(db: Session = Depends(get_db), who: Principal = Depends(require_admin)):
    _group_wide(who)
    out = []
    for s in registry.describe(db=db):
        last = db.scalar(select(IngestionRun).where(IngestionRun.source == s["source"])
                         .order_by(IngestionRun.id.desc()).limit(1))
        # Where the newest data really came from: a source that says its data is AI-made (the mock systems) is labelled.
        latest = db.scalar(select(KpiRecord).where(KpiRecord.source == s["source"]).order_by(KpiRecord.id.desc()).limit(1))
        origin = ((latest.detail or {}).get("origin") if latest else None)
        out.append({**s, "data_origin": origin, "last_run": None if last is None else {
            "period": last.period, "status": last.status, "mode": last.mode,
            "companies_ok": last.companies_ok, "companies_failed": last.companies_failed,
            "records_written": last.records_written, "finished_at": last.finished_at}})
    return out


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
    alerts_engine.safe_evaluate(db, req.period)
    audit(db, who, "ingestion_run", req.period, {"sources": [s.source for s in summaries]})
    db.commit()
    return [{**asdict(s), "errors": s.errors[:20]} for s in summaries]
