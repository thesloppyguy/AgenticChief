"""Small persisted workflow engine: ordered steps, each output saved before the next starts.

A run that dies mid-way (restart, crash) is marked interrupted and resumes after its last finished step.
Steps must be deterministic given the saved state of earlier steps, so skipping them on resume is safe.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import Principal, Role
from app.db.models import WorkflowEvent, WorkflowRun

STARTABLE = ("queued", "interrupted", "failed")
TERMINAL = ("succeeded", "failed")


@dataclass
class StepCtx:
    db: Session
    run: WorkflowRun
    who: Principal
    state: dict[str, Any]  # outputs of the steps that already finished
    deps: dict[str, Any] = field(default_factory=dict)  # injected services (e.g. the LLM client)


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    run: Callable[[StepCtx], dict]


@dataclass(frozen=True)
class WorkflowDef:
    key: str
    title: str
    steps: tuple[Step, ...]
    finalize: Callable[[StepCtx], dict]  # builds the run's result from the final state


def _now() -> datetime:
    return datetime.now(UTC)


def emit(db: Session, run_id: int, step: str, status: str, message: str, data: dict | None = None) -> None:
    seq = (db.scalar(select(func.max(WorkflowEvent.seq)).where(WorkflowEvent.run_id == run_id)) or 0) + 1
    db.add(WorkflowEvent(run_id=run_id, seq=seq, step=step, status=status, message=message[:300], data=data))


def create_run(db: Session, who: Principal, wf: WorkflowDef, period: str, params: dict | None = None) -> WorkflowRun:
    run = WorkflowRun(workflow=wf.key, period=period, status="queued", params=params,
                      requested_by=who.user_id, role=who.role.value, state={})
    db.add(run)
    db.flush()
    emit(db, run.id, "run", "done", f"{wf.title} queued for {period}")
    db.commit()
    return run


def sweep_stale(db: Session, stale_after_s: int | None = None) -> int:
    """Runs that say 'running' but stopped heartbeating were killed mid-flight: mark them interrupted."""
    cutoff = _now() - timedelta(seconds=settings.workflow_stale_after_s if stale_after_s is None else stale_after_s)
    stale = db.scalars(select(WorkflowRun).where(
        WorkflowRun.status == "running",
        (WorkflowRun.heartbeat_at.is_(None)) | (WorkflowRun.heartbeat_at < cutoff))).all()
    for r in stale:
        r.status = "interrupted"
        emit(db, r.id, "run", "failed", "interrupted: the worker stopped; resume to continue")
    db.commit()
    return len(stale)


def execute(factory: sessionmaker, wf: WorkflowDef, run_id: int, deps: dict[str, Any] | None = None,
            on_failure: Callable[[Session, WorkflowRun], None] | None = None) -> str:
    """Run (or resume) a workflow in its own session. Returns the final status."""
    with factory() as db:
        # Atomic claim: only one worker may move a run into 'running'.
        claimed = db.execute(update(WorkflowRun)
                             .where(WorkflowRun.id == run_id, WorkflowRun.status.in_(STARTABLE))
                             .values(status="running", heartbeat_at=_now(), error=None, finished_at=None)).rowcount
        db.commit()
        run = db.get(WorkflowRun, run_id)
        if claimed != 1 or run is None:
            return run.status if run else "missing"
        who = Principal(run.requested_by, Role(run.role), None)
        state = dict(run.state or {})
        ctx = StepCtx(db, run, who, state, deps or {})
        emit(db, run.id, "run", "started", "resuming" if state else "started")
        db.commit()
        for step in wf.steps:
            if step.key in state:
                emit(db, run.id, step.key, "skipped", f"{step.label}: already done")
                continue
            emit(db, run.id, step.key, "started", step.label)
            db.commit()
            try:
                out = step.run(ctx)
            except Exception as e:  # noqa: BLE001 - recorded by type only, never the message
                db.rollback()
                run = db.get(WorkflowRun, run_id)
                run.status, run.error, run.finished_at = "failed", type(e).__name__, _now()
                emit(db, run.id, step.key, "failed", f"{step.label} failed: {type(e).__name__}")
                db.commit()
                if on_failure:
                    on_failure(db, run)
                return "failed"
            state[step.key] = out
            run.state = dict(state)  # new dict so the JSON column change is detected
            run.heartbeat_at = _now()
            emit(db, run.id, step.key, "done", step.label)
            db.commit()
        run.result = wf.finalize(ctx)
        run.status, run.finished_at, run.heartbeat_at = "succeeded", _now(), _now()
        emit(db, run.id, "run", "done", "completed")
        db.commit()
        return "succeeded"
