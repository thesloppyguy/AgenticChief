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
    status = wf_engine.execute(factory, monthly_review.WORKFLOW, run.id,
                               {"llm": deps.get("llm"), "allm": deps.get("allm")})
    if status != "succeeded":
        raise JobFailed(f"{period}: review run #{run.id} {status}")
    return f"{period}: review run #{run.id} completed (publishing still needs approval)"


def job_watch(db: Session, params: dict, now: datetime, deps: dict[str, Any]) -> str:
    """Check one user-defined watch. A watch that never fires is as suspicious as one that fires
    constantly, so the detail string always records what was observed."""
    from app.alerts import watches
    from app.db.models import Watch

    period = resolve_period(params.get("period", "current"), now)
    w = db.get(Watch, params.get("watch_id"))
    if w is None:
        raise JobFailed("the watch no longer exists")
    if not w.enabled:
        return f"{period}: watch disabled"
    seen = watches.observe(db, w, period)
    alert = watches.evaluate(db, w, period)
    db.commit()  # evaluate() leaves the transaction to its caller, as alerts.engine._raise does
    # "Still breaching, already alerted" must not read as "no breach", or an operator scanning the
    # schedule log would think the condition had cleared.
    if alert:
        outcome = "fired"
    elif seen["would_fire"]:
        outcome = "still breaching (already alerted this period)"
    else:
        outcome = "no breach"
    return f"{period}: {outcome} (observed {seen['observed']})"


def job_workflow(db: Session, params: dict, now: datetime, deps: dict[str, Any]) -> str:
    """Run a published, prompt-authored workflow unattended.

    The published version is resolved at run time, so a rollback takes effect on the next run and a
    deprecation stops the schedule outright. Anything the workflow proposes is filed as "scheduler",
    which means no human can ever approve something they themselves set in motion.
    """
    from app.assets import service as asset_service
    from app.assets.service import AssetError
    from app.workflows.compiler import compile_spec
    from app.workflows.spec import WorkflowSpec

    period = resolve_period(params.get("period", "previous"), now)
    try:
        a = asset_service.get(db, "workflow", params.get("workflow_key", ""))
    except AssetError as e:
        raise JobFailed(e.message) from e
    if a.deprecated or a.published_version is None:
        raise JobFailed("the workflow is no longer published")
    row = asset_service.version_row(db, a, a.published_version)
    wf = compile_spec(a.key, WorkflowSpec(**row.definition))
    run = wf_engine.create_run(db, SCHEDULER, wf, period,
                               {"asset_id": a.id, "asset_version": a.published_version})
    factory: sessionmaker = deps["factory"]
    status = wf_engine.execute(factory, wf, run.id,
                               {"llm": deps.get("llm"), "allm": deps.get("allm")})
    if status != "succeeded":
        raise JobFailed(f"{period}: run #{run.id} {status}")
    return f"{period}: {a.key} run #{run.id} completed"


JOBS = {"ingest": job_ingest, "monthly_review": job_monthly_review, "watch": job_watch,
        "workflow": job_workflow}
