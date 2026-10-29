from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.alerts import engine as alerts_engine
from app.core.config import settings
from app.core.security import Principal, get_principal
from app.db.models import WorkflowEvent, WorkflowRun
from app.db.session import SessionLocal, get_db
from app.reports import monthly_review
from app.reports.markdown import render_markdown
from app.reports.pdf import render_pdf
from app.workflows import engine

router = APIRouter(prefix="/workflows")


def get_session_factory() -> sessionmaker:
    return SessionLocal


def get_llm():
    """A client for the commentary step, or None (then a deterministic template is used)."""
    if not settings.anthropic_api_key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)


def _group_wide(who: Principal) -> None:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")


def _on_failure(db: Session, run: WorkflowRun) -> None:
    """A failed report should not be silent."""
    alerts_engine._raise(db, kind="workflow_failed", severity="medium", company_id=None, entity="monthly_review",
                         period=run.period, title=f"Monthly review for {run.period} failed ({run.error})",
                         detail={"run_id": run.id, "error": run.error}, dedupe_key=f"workflow:{run.id}:{run.error}")
    db.commit()


def _launch(bg: BackgroundTasks, factory: sessionmaker, llm, run_id: int) -> None:
    bg.add_task(engine.execute, factory, monthly_review.WORKFLOW, run_id, {"llm": llm}, _on_failure)


def _summary(r: WorkflowRun) -> dict:
    return {"id": r.id, "workflow": r.workflow, "period": r.period, "status": r.status, "error": r.error,
            "requested_by": r.requested_by, "created_at": r.created_at, "finished_at": r.finished_at}


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
                      for s in monthly_review.WORKFLOW.steps],
            "events": [{"seq": e.seq, "at": e.at, "step": e.step, "status": e.status, "message": e.message}
                       for e in events],
            "result": run.result if run.status == "succeeded" else None}


@router.post("/runs/{run_id}/resume", status_code=202)
def resume(run_id: int, bg: BackgroundTasks, db: Session = Depends(get_db),
           who: Principal = Depends(get_principal), factory: sessionmaker = Depends(get_session_factory),
           llm=Depends(get_llm)):
    run = _load(db, who, run_id)
    if run.status not in engine.STARTABLE or run.status == "queued":
        raise HTTPException(409, f"A {run.status} run cannot be resumed")
    _launch(bg, factory, llm, run.id)
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
