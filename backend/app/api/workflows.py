from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.alerts import engine as alerts_engine
from app.assets import service as asset_service
from app.assets.service import AssetError
from app.core.config import settings
from app.core.security import Principal, get_principal
from app.db.models import Asset, WorkflowEvent, WorkflowRun
from app.db.session import SessionLocal, get_db
from app.reports import monthly_review
from app.reports.markdown import render_markdown
from app.reports.pdf import render_pdf
from app.services.scorecard import current_period
from app.workflows import engine, planner
from app.workflows.compiler import compile_spec
from app.workflows.spec import WorkflowSpec

router = APIRouter(prefix="/workflows")


def get_session_factory() -> sessionmaker:
    return SessionLocal


def get_llm():
    """A client for the commentary step, or None (then a deterministic template is used)."""
    if not settings.anthropic_api_key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)


def get_planner_client():
    """The planner needs a live model, so an unconfigured deployment gets a clear 503 rather than a
    silent template. Defined here, not imported from api.copilot: that module imports this one."""
    if not settings.anthropic_api_key:
        raise HTTPException(503, "Workflow planning is not configured (ANTHROPIC_API_KEY)")
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def get_async_llm():
    """chat_turn streams, so skill and agent steps need the async client; commentary needs the sync
    one. Both are injected, and both are None in tests."""
    if not settings.anthropic_api_key:
        return None
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _group_wide(who: Principal) -> None:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")


def _on_failure(db: Session, run: WorkflowRun) -> None:
    """A failed report should not be silent."""
    alerts_engine._raise(db, kind="workflow_failed", severity="medium", company_id=None, entity="monthly_review",
                         period=run.period, title=f"Monthly review for {run.period} failed ({run.error})",
                         detail={"run_id": run.id, "error": run.error}, dedupe_key=f"workflow:{run.id}:{run.error}")
    db.commit()


def _launch(bg: BackgroundTasks, factory: sessionmaker, llm, run_id: int, wf=None, allm=None) -> None:
    bg.add_task(engine.execute, factory, wf or monthly_review.WORKFLOW, run_id,
                {"llm": llm, "allm": allm}, _on_failure)


def _summary(r: WorkflowRun) -> dict:
    return {"id": r.id, "workflow": r.workflow, "period": r.period, "status": r.status, "error": r.error,
            "requested_by": r.requested_by, "created_at": r.created_at, "finished_at": r.finished_at}


def _workflow_for(db: Session, run: WorkflowRun):
    """The definition a run belongs to. A prompt-authored run pins the asset version it started with,
    so republishing the workflow mid-run cannot swap the steps under a run that is resuming."""
    key = run.workflow[4:] if run.workflow.startswith("def:") else run.workflow
    if key == monthly_review.KEY or run.workflow == monthly_review.KEY:
        return monthly_review.WORKFLOW

    asset = db.scalar(select(Asset).where(Asset.kind == "workflow", Asset.key == key))
    if asset is None:
        # Legacy / unknown keys must not silently render as the monthly review.
        if run.workflow.startswith("def:"):
            raise HTTPException(409, "the version this run started with is no longer available")
        return monthly_review.WORKFLOW

    version = (run.params or {}).get("asset_version") or asset.published_version or asset.version
    row = asset_service.version_row(db, asset, version) if version else None
    if row is None:
        raise HTTPException(409, "the version this run started with is no longer available")
    return compile_spec(key, WorkflowSpec(**row.definition))


def _load(db: Session, who: Principal, run_id: int) -> WorkflowRun:
    _group_wide(who)
    engine.sweep_stale(db)
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


class StartRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.post("/monthly-review/runs", status_code=202)
def start(req: StartRequest, bg: BackgroundTasks, db: Session = Depends(get_db),
          who: Principal = Depends(get_principal), factory: sessionmaker = Depends(get_session_factory),
          llm=Depends(get_llm)):
    _group_wide(who)
    run = engine.create_run(db, who, monthly_review.WORKFLOW, req.period)
    _launch(bg, factory, llm, run.id)
    return _summary(run)


@router.get("/runs")
def runs(limit: int = 50, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    _group_wide(who)
    engine.sweep_stale(db)
    rows = db.scalars(select(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(min(limit, 200)))
    return [_summary(r) for r in rows]


@router.get("/runs/{run_id}")
def run_detail(run_id: int, after_seq: int = 0, db: Session = Depends(get_db),
               who: Principal = Depends(get_principal)):
    run = _load(db, who, run_id)
    events = db.scalars(select(WorkflowEvent).where(WorkflowEvent.run_id == run_id, WorkflowEvent.seq > after_seq)
                        .order_by(WorkflowEvent.seq))
    return {**_summary(run),
            "steps": [{"key": s.key, "label": s.label, "done": s.key in (run.state or {})}
                      for s in _workflow_for(db, run).steps],
            "events": [{"seq": e.seq, "at": e.at, "step": e.step, "status": e.status, "message": e.message}
                       for e in events],
            "result": run.result if run.status == "succeeded" else None}


@router.post("/runs/{run_id}/resume", status_code=202)
def resume(run_id: int, bg: BackgroundTasks, db: Session = Depends(get_db),
           who: Principal = Depends(get_principal), factory: sessionmaker = Depends(get_session_factory),
           llm=Depends(get_llm), allm=Depends(get_async_llm)):
    run = _load(db, who, run_id)
    if run.status not in engine.STARTABLE or run.status == "queued":
        raise HTTPException(409, f"A {run.status} run cannot be resumed")
    _launch(bg, factory, llm, run.id, _workflow_for(db, run), allm)
    return _summary(run)


@router.get("/runs/{run_id}/markdown", response_class=PlainTextResponse)
def run_markdown(run_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    run = _load(db, who, run_id)
    if run.status != "succeeded":
        raise HTTPException(409, "The report is not finished")
    return render_markdown(run.result)



@router.get("/runs/{run_id}/pdf")
def run_pdf(run_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    run = _load(db, who, run_id)
    if run.status != "succeeded":
        raise HTTPException(409, "The report is not finished")
    return Response(render_pdf(run.result), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="monthly-review-{run.period}.pdf"'})


# --- workflow definitions ------------------------------------------------------------------------
# Stored as assets with kind="workflow", so they inherit draft -> validate -> publish-by-a-second-admin,
# rollback, deprecation and audit for free. Namespaced under /defs so they cannot collide with /runs.


def _author(who: Principal = Depends(get_principal)) -> Principal:
    """Authoring, running and scheduling a workflow are all group-wide. The engine runs every step as
    a group-wide principal (engine.py:92), so a scoped user must never be able to start one."""
    if who.role.value not in ("admin", "editor") or who.company_ids is not None:
        raise HTTPException(403, "Group-wide editor or admin access is required")
    return who


class DraftRequest(BaseModel):
    description: str = Field(min_length=10, max_length=4000)
    period: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class DefIn(BaseModel):
    key: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    definition: dict


class DefVersionIn(BaseModel):
    definition: dict


def _def_out(db: Session, a: Asset, detail: bool = False) -> dict:
    shown = a.published_version or a.version
    row = asset_service.version_row(db, a, shown)
    spec = WorkflowSpec(**row.definition) if row else None
    out = {"id": a.id, "key": a.key, "name": a.name, "description": a.description,
           "lifecycle": a.lifecycle, "version": a.version, "published_version": a.published_version,
           "title": spec.title if spec else None,
           "steps": [s.model_dump() for s in spec.steps] if spec else [],
           "uses": spec.tools if spec else [], "permissions": spec.permissions if spec else []}
    if detail:
        out["definition"] = asset_service.latest(db, a).definition
        out["validation"] = a.validation
    return out


@router.post("/drafts")
async def draft_workflow(req: DraftRequest, db: Session = Depends(get_db),
                         who: Principal = Depends(_author), client=Depends(get_planner_client)):
    """Plan a workflow from a description. The result is a draft to review: nothing is saved here."""
    return await planner.draft(client, db, who, req.description, req.period or current_period())


@router.get("/defs")
def list_defs(db: Session = Depends(get_db), who: Principal = Depends(_author)):
    rows = db.scalars(select(Asset).where(Asset.kind == "workflow").order_by(Asset.name))
    return [_def_out(db, a) for a in rows]


@router.get("/defs/{key}")
def get_def(key: str, db: Session = Depends(get_db), who: Principal = Depends(_author)):
    try:
        return _def_out(db, asset_service.get(db, "workflow", key), detail=True)
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e


@router.post("/defs", status_code=201)
def create_def(body: DefIn, db: Session = Depends(get_db), who: Principal = Depends(_author)):
    try:
        a = asset_service.create(db, who, "workflow", body.key, body.name, body.description, body.definition)
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e
    return _def_out(db, a, detail=True)


@router.post("/defs/{key}/versions", status_code=201)
def add_def_version(key: str, body: DefVersionIn, db: Session = Depends(get_db),
                    who: Principal = Depends(_author)):
    try:
        a = asset_service.new_version(db, who, asset_service.get(db, "workflow", key), body.definition)
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e
    return _def_out(db, a, detail=True)


@router.post("/defs/{key}/validate")
def validate_def(key: str, db: Session = Depends(get_db), who: Principal = Depends(_author)):
    try:
        a = asset_service.get(db, "workflow", key)
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e
    return {"validation": asset_service.validate(db, who, a), "lifecycle": a.lifecycle}


@router.post("/defs/{key}/deprecate")
def deprecate_def(key: str, db: Session = Depends(get_db), who: Principal = Depends(_author)):
    if who.role.value != "admin":
        raise HTTPException(403, "Admin role required")
    try:
        a = asset_service.deprecate(db, who, asset_service.get(db, "workflow", key))
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e
    return _def_out(db, a)


class DefRunRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    allow_draft: bool = False  # admins only, for trying a version before it is published


@router.post("/defs/{key}/runs", status_code=202)
def run_def(key: str, body: DefRunRequest, bg: BackgroundTasks, db: Session = Depends(get_db),
            who: Principal = Depends(_author), factory: sessionmaker = Depends(get_session_factory),
            llm=Depends(get_llm), allm=Depends(get_async_llm)):
    try:
        a = asset_service.get(db, "workflow", key)
    except AssetError as e:
        raise HTTPException(e.status, e.message) from e
    if a.deprecated:
        raise HTTPException(409, "this workflow has been deprecated")
    version = a.version if (body.allow_draft and who.role.value == "admin") else a.published_version
    if version is None:
        raise HTTPException(409, "this workflow is not published yet")
    row = asset_service.version_row(db, a, version)
    wf = compile_spec(key, WorkflowSpec(**row.definition))
    # Pin the version: a republish mid-run must not swap the steps under a run that resumes.
    run = engine.create_run(db, who, wf, body.period, {"asset_id": a.id, "asset_version": version})
    _launch(bg, factory, llm, run.id, wf, allm)
    return _summary(run)
