"""Pull raw counts from each source, convert, and upsert KPI records with lineage."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, IngestionRun, KpiRecord

from .base import Extractor
from .raw import RawDataError, to_metric

MAX_ERRORS_KEPT = 200


@dataclass
class SourceSummary:
    source: str
    mode: str
    status: str
    companies_ok: int = 0
    companies_failed: int = 0
    records_written: int = 0
    errors: list[dict] = field(default_factory=list)
    run_id: int | None = None


def ingest(
    db: Session,
    period: str,
    extractors: dict[str, Extractor],
    sources: list[str] | None = None,
    company_codes: list[str] | None = None,
) -> list[SourceSummary]:
    q = select(Company).where(Company.active).order_by(Company.code)
    companies = [c for c in db.scalars(q) if company_codes is None or c.code in company_codes]
    out: list[SourceSummary] = []
    for source, ex in extractors.items():
        if sources is not None and source not in sources:
            continue
        out.append(_ingest_source(db, period, ex, companies))
    return out


def _ingest_source(db: Session, period: str, ex: Extractor, companies: list[Company]) -> SourceSummary:
    run = IngestionRun(source=ex.source, mode=ex.mode, period=period, status="running")
    db.add(run)
    db.commit()
    s = SourceSummary(ex.source, ex.mode, "running", run_id=run.id)

    existing = {
        (r.company_id, r.kpi_key): r
        for r in db.scalars(select(KpiRecord).where(
            KpiRecord.period == period, KpiRecord.kpi_key.in_(ex.kpis),
            KpiRecord.company_id.in_([c.id for c in companies])))
    }

    for c in companies:
        failed = False
        try:
            fetched = ex.fetch(c.code, period)
        except Exception as e:  # noqa: BLE001 - one company must not stop the run
            s.companies_failed += 1
            s.errors.append({"company": c.code, "error": type(e).__name__})
            continue
        for kpi, raw in fetched.items():
            if kpi not in ex.kpis:  # an extractor may only write KPIs it owns (never manual ones)
                failed = True
                s.errors.append({"company": c.code, "kpi": kpi, "error": "kpi_not_owned_by_source"})
                continue
            try:
                m = to_metric(kpi, raw)
            except RawDataError:
                failed = True
                s.errors.append({"company": c.code, "kpi": kpi, "error": "invalid_raw_data"})
                continue
            rec = existing.get((c.id, kpi))
            if rec is not None and rec.source == "manual":
                continue
            if rec is None:
                rec = KpiRecord(company_id=c.id, kpi_key=kpi, period=period, source=ex.source)
                db.add(rec)
                existing[(c.id, kpi)] = rec
            rec.achievement, rec.numerator, rec.denominator = m.achievement, m.numerator, m.denominator
            rec.source = ex.source
            rec.detail = {"mode": ex.mode, "run_id": run.id, "raw": raw, **ex.lineage_for(kpi)}
            rec.ingested_at = datetime.now(UTC)
            s.records_written += 1
        s.companies_failed += failed
        s.companies_ok += not failed
        db.commit()

    s.status = ("success" if s.companies_failed == 0
                else "failed" if s.companies_ok == 0 else "partial")
    run.status, run.companies_ok, run.companies_failed = s.status, s.companies_ok, s.companies_failed
    run.records_written, run.errors = s.records_written, s.errors[:MAX_ERRORS_KEPT]
    run.finished_at = datetime.now(UTC)
    db.commit()
    return s
