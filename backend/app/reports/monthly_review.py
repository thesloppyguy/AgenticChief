"""The monthly leadership review as a persisted workflow: collect -> lineage -> build -> commentary."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.alerts.engine import prev_period
from app.db.models import IngestionRun, KpiRecord
from app.ingestion import registry
from app.services.scorecard import build_scorecard
from app.workflows.engine import Step, StepCtx, WorkflowDef

from . import commentary
from .builder import build_report

KEY = "monthly_review"


def _collect(ctx: StepCtx) -> dict:
    period = ctx.run.period
    prev = prev_period(period)
    return {"card": build_scorecard(ctx.db, ctx.who, period),
            "prev": build_scorecard(ctx.db, ctx.who, prev) if prev else None}


def _lineage(ctx: StepCtx) -> dict:
    db, period = ctx.db, ctx.run.period
    sources = []
    for s in registry.describe(db=db):
        last = db.scalar(select(IngestionRun).where(IngestionRun.source == s["source"],
                                                    IngestionRun.period == period).order_by(IngestionRun.id.desc()).limit(1))
        sources.append({
            "source": s["source"], "label": s["label"], "mode": s["mode"], "kpis": s["kpis"],
            "no_source_kpis": s["no_source_kpis"],
            "last_run": None if last is None else {
                "status": last.status, "companies_ok": last.companies_ok, "companies_failed": last.companies_failed,
                "records_written": last.records_written,
                "finished_at": last.finished_at.isoformat() if last.finished_at else None}})
    origin: dict[str, int] = {}
    for src, detail in db.execute(select(KpiRecord.source, KpiRecord.detail).where(KpiRecord.period == period)):
        d = detail or {}
        kind = "ai_generated" if d.get("origin") in ("ai", "fallback") else \
            "manual" if src == "manual" else src if src in ("seed", "demo") else \
            ((detail or {}).get("mode") if (detail or {}).get("mode") in ("stub", "registry") else "live")
        origin[kind] = origin.get(kind, 0) + 1
    return {"sources": sources, "data_origin": origin}


def _build(ctx: StepCtx) -> dict:
    c = ctx.state["collect"]
    return build_report(ctx.run.period, prev_period(ctx.run.period), c["card"], c["prev"],
                        ctx.state["lineage"], ctx.run.requested_by, datetime.now(UTC).isoformat(timespec="seconds"))


def _commentary(ctx: StepCtx) -> dict:
    return commentary.generate(ctx.deps.get("llm"), ctx.state["build"])


def _finalize(ctx: StepCtx) -> dict:
    return {**ctx.state["build"], "commentary": ctx.state["commentary"]}


WORKFLOW = WorkflowDef(
    KEY, "Monthly leadership review",
    (Step("collect", "Collect scorecards (this month and last)", _collect),
     Step("lineage", "Gather source lineage and data origin", _lineage),
     Step("build", "Build report: comparisons and exceptions", _build),
     Step("commentary", "Draft and verify commentary", _commentary)),
    _finalize,
)
