"""Source health and freshness for ingestion status, Copilot, and the Connections UI."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import IngestionRun, KpiRecord
from app.ingestion import registry


def _age_hours(when: datetime | None, now: datetime) -> float | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (now - when).total_seconds() / 3600.0)


def _freshness(age_hours: float | None, sla_hours: float) -> str:
    if age_hours is None:
        return "never"
    if age_hours <= sla_hours:
        return "fresh"
    return "stale"


def enrich_source(db: Session, described: dict, *, now: datetime | None = None,
                  sla_hours: float | None = None) -> dict:
    """Add last_run, data_origin and freshness fields onto a registry.describe() row."""
    now = now or datetime.now(UTC)
    sla = settings.source_freshness_sla_hours if sla_hours is None else sla_hours
    source = described["source"]
    last = db.scalar(
        select(IngestionRun).where(IngestionRun.source == source).order_by(IngestionRun.id.desc()).limit(1)
    )
    latest = db.scalar(
        select(KpiRecord).where(KpiRecord.source == source).order_by(KpiRecord.id.desc()).limit(1)
    )
    origin = ((latest.detail or {}).get("origin") if latest else None)
    # Prefer a successful run's finish time; fall back to the newest KPI write for that source.
    as_of = None
    if last is not None and last.status in ("success", "partial") and last.finished_at is not None:
        as_of = last.finished_at
    elif latest is not None:
        as_of = latest.ingested_at
    age = _age_hours(as_of, now)
    return {
        **described,
        "data_origin": origin,
        "last_run": None if last is None else {
            "period": last.period,
            "status": last.status,
            "mode": last.mode,
            "companies_ok": last.companies_ok,
            "companies_failed": last.companies_failed,
            "records_written": last.records_written,
            "finished_at": last.finished_at,
        },
        "freshness": _freshness(age, sla),
        "age_hours": None if age is None else round(age, 2),
        "as_of": as_of,
        "sla_hours": sla,
    }


def build_sources_list(db: Session, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    return [enrich_source(db, s, now=now) for s in registry.describe(db=db)]


def build_sources_status(db: Session, *, now: datetime | None = None) -> dict:
    """Full envelope for GET /sources/status."""
    now = now or datetime.now(UTC)
    sources = build_sources_list(db, now=now)
    return {
        "mock_sources_enabled": settings.mock_sources_enabled,
        "ai_configured": bool(settings.anthropic_api_key),
        "stub_data_enabled": settings.stub_data_enabled,
        "sla_hours": settings.source_freshness_sla_hours,
        "as_of": now,
        "sources": sources,
    }


def freshness_summary(db: Session, *, now: datetime | None = None) -> dict:
    """Compact block attached to scorecard payloads."""
    status = build_sources_status(db, now=now)
    sources = status["sources"]
    counts = {"fresh": 0, "stale": 0, "never": 0}
    for s in sources:
        counts[s["freshness"]] = counts.get(s["freshness"], 0) + 1
    overall = "fresh"
    if counts["stale"] or counts["never"]:
        overall = "stale" if counts["stale"] else "never"
        if counts["stale"] and counts["never"]:
            overall = "partial"
        elif counts["fresh"] and (counts["stale"] or counts["never"]):
            overall = "partial"
    return {
        "overall": overall,
        "sla_hours": status["sla_hours"],
        "mock_sources_enabled": status["mock_sources_enabled"],
        "counts": counts,
        "sources": [
            {
                "source": s["source"],
                "label": s["label"],
                "mode": s["mode"],
                "freshness": s["freshness"],
                "age_hours": s["age_hours"],
                "data_origin": s["data_origin"],
                "last_status": (s["last_run"] or {}).get("status") if s["last_run"] else None,
            }
            for s in sources
        ],
    }
