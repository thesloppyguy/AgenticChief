"""What a scheduled job does. Each takes a session, its params, `now` and shared deps, and returns a
short detail string; raising JobFailed marks the run failed."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.alerts import engine as alerts_engine
from app.core.security import Principal, Role
from app.ingestion import registry
from app.ingestion.runner import ingest
from app.reports import monthly_review
from app.workflows import engine as wf_engine

SCHEDULER = Principal("scheduler", Role.VIEWER, None)


class JobFailed(Exception):
    pass


def resolve_period(which: str, now: datetime) -> str:
    if which == "current":
        return f"{now.year}-{now.month:02d}"
    if which == "previous":
        y, m = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
        return f"{y}-{m:02d}"
    if len(which) == 7 and which[4] == "-":  # an explicit YYYY-MM
        return which
    raise JobFailed("params.period must be current, previous or YYYY-MM")


def job_ingest(db: Session, params: dict, now: datetime, deps: dict[str, Any]) -> str:
    period = resolve_period(params.get("period", "current"), now)
    summaries = ingest(db, period, registry.build_extractors(db=db), params.get("sources"))
    alerts_engine.on_ingestion(db, summaries, period)
    alerts_engine.safe_evaluate(db, period)
    records = sum(s.records_written for s in summaries)
    failed = [s.source for s in summaries if s.status == "failed"]
    if failed:
        raise JobFailed(f"{period}: ingestion failed for {', '.join(failed)}")
    return f"{period}: {len(summaries)} sources, {records} records"


def job_monthly_review(db: Session, params: dict, now: datetime, deps: dict[str, Any]) -> str:
    period = resolve_period(params.get("period", "previous"), now)
    run = wf_engine.create_run(db, SCHEDULER, monthly_review.WORKFLOW, period)
    factory: sessionmaker = deps["factory"]
    status = wf_engine.execute(factory, monthly_review.WORKFLOW, run.id, {"llm": deps.get("llm")})
    if status != "succeeded":
        raise JobFailed(f"{period}: review run #{run.id} {status}")
    return f"{period}: review run #{run.id} completed (publishing still needs approval)"


JOBS = {"ingest": job_ingest, "monthly_review": job_monthly_review}
