"""Shared workflow definition ops for the HTTP API and Copilot tools."""
from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.alerts import engine as alerts_engine
from app.assets import service as asset_service
from app.assets.service import AssetError
from app.core.security import Principal
from app.db.models import Asset, WorkflowRun
from app.workflows import engine
from app.workflows.compiler import compile_spec
from app.workflows.spec import WorkflowSpec


class WorkflowOpsError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def require_author(who: Principal) -> str | None:
    """Return an error message if who cannot author/list/run workflow defs; else None."""
    if who.role.value not in ("admin", "editor") or who.company_ids is not None:
        return "Group-wide editor or admin access is required"
    return None


def def_out(db: Session, a: Asset, detail: bool = False) -> dict:
    shown = a.published_version or a.version
    row = asset_service.version_row(db, a, shown)
    spec = WorkflowSpec(**row.definition) if row else None
    out = {
        "id": a.id,
        "key": a.key,
        "name": a.name,
        "description": a.description,
        "lifecycle": a.lifecycle,
        "version": a.version,
        "published_version": a.published_version,
        "title": spec.title if spec else None,
        "steps": [s.model_dump() for s in spec.steps] if spec else [],
        "uses": spec.tools if spec else [],
        "permissions": spec.permissions if spec else [],
    }
    if detail:
        out["definition"] = asset_service.latest(db, a).definition
        out["validation"] = a.validation
    return out


def list_defs(db: Session, lifecycle: str | None = None) -> list[dict]:
    rows = list(db.scalars(select(Asset).where(Asset.kind == "workflow").order_by(Asset.name)))
    out = [def_out(db, a) for a in rows]
    if lifecycle:
        want = lifecycle.strip().lower()
        out = [r for r in out if (r.get("lifecycle") or "").lower() == want]
    return out


def save_def(
    db: Session,
    who: Principal,
    key: str,
    name: str,
    description: str,
    definition: dict,
) -> dict:
    try:
        a = asset_service.create(db, who, "workflow", key, name, description, definition)
    except AssetError as e:
        raise WorkflowOpsError(e.status, e.message) from e
    return def_out(db, a, detail=True)


def run_summary(r: WorkflowRun) -> dict:
    return {
        "id": r.id,
        "workflow": r.workflow,
        "period": r.period,
        "status": r.status,
        "error": r.error,
        "requested_by": r.requested_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def resolve_run_version(
    db: Session,
    who: Principal,
    key: str,
    *,
    allow_draft: bool = False,
) -> tuple[Asset, int, Any]:
    """Return (asset, version, compiled WorkflowDef). Raises WorkflowOpsError."""
    try:
        a = asset_service.get(db, "workflow", key)
    except AssetError as e:
        raise WorkflowOpsError(e.status, e.message) from e
    if a.deprecated:
        raise WorkflowOpsError(409, "this workflow has been deprecated")
    version = a.version if (allow_draft and who.role.value == "admin") else a.published_version
    if version is None:
        raise WorkflowOpsError(409, "this workflow is not published yet")
    row = asset_service.version_row(db, a, version)
    if row is None:
        raise WorkflowOpsError(409, "the requested workflow version is missing")
    wf = compile_spec(key, WorkflowSpec(**row.definition))
    return a, version, wf


def start_run(
    db: Session,
    who: Principal,
    key: str,
    period: str,
    *,
    allow_draft: bool = False,
    commit: bool = True,
) -> tuple[WorkflowRun, Any]:
    a, version, wf = resolve_run_version(db, who, key, allow_draft=allow_draft)
    run = engine.create_run(
        db,
        who,
        wf,
        period,
        {"asset_id": a.id, "asset_version": version},
        commit=commit,
    )
    return run, wf


def on_run_failure(db: Session, run: WorkflowRun) -> None:
    alerts_engine._raise(
        db,
        kind="workflow_failed",
        severity="medium",
        company_id=None,
        entity="monthly_review",
        period=run.period,
        title=f"Monthly review for {run.period} failed ({run.error})",
        detail={"run_id": run.id, "error": run.error},
        dedupe_key=f"workflow:{run.id}:{run.error}",
    )
    db.commit()


def queue_execute(
    factory: sessionmaker,
    wf: Any,
    run_id: int,
    llm: Any = None,
    allm: Any = None,
) -> None:
    """Fire-and-forget execute (for Approvals, which have no FastAPI BackgroundTasks)."""

    def _run() -> None:
        engine.execute(
            factory,
            wf,
            run_id,
            {"llm": llm, "allm": allm},
            on_run_failure,
        )

    t = threading.Thread(target=_run, name=f"workflow-run-{run_id}", daemon=True)
    t.start()
