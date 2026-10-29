from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import service
from app.approvals.actions import ACTIONS
from app.approvals.service import ApprovalError
from app.core.security import Principal, get_principal
from app.db.models import ApprovalEvent, ApprovalRequest
from app.db.session import get_db

router = APIRouter(prefix="/approvals")


def _http(e: ApprovalError) -> HTTPException:
    return HTTPException(e.status, e.message)


def _out(r: ApprovalRequest) -> dict:
    return {"id": r.id, "action": r.action, "risk": r.risk, "summary": r.summary, "status": r.status,
            "requested_by": r.requested_by, "via": r.via, "session_id": r.session_id, "args": r.args,
            "context": r.context, "created_at": r.created_at, "decided_by": r.decided_by,
            "decided_at": r.decided_at, "decision_comment": r.decision_comment, "result": r.result}


@router.get("/actions")
def actions(_: Principal = Depends(get_principal)):
    return [{"key": a.key, "risk": a.risk.value, "description": a.description,
             "args_schema": a.args_model.model_json_schema(), "group_wide_only": a.group_wide_only}
            for a in ACTIONS.values()]


class SubmitRequest(BaseModel):
    action: str
    args: dict = Field(default_factory=dict)
    context: dict | None = None


@router.post("", status_code=201)
def submit(req: SubmitRequest, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    try:
        res = service.submit(db, who, req.action, req.args, via="api", context=req.context)
    except ApprovalError as e:
        raise _http(e) from e
    return {"verdict": res.verdict, "reason": res.reason, "approval": _out(res.approval)}


@router.get("")
def list_approvals(status: str | None = None, db: Session = Depends(get_db),
                   who: Principal = Depends(get_principal)):
    return [_out(r) for r in service.list_for(db, who, status)]


@router.get("/{approval_id}")
def get_approval(approval_id: int, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
    try:
        r = service.get_visible(db, who, approval_id)
    except ApprovalError as e:
        raise _http(e) from e
    events = db.scalars(select(ApprovalEvent).where(ApprovalEvent.approval_id == r.id).order_by(ApprovalEvent.id))
    return {**_out(r), "events": [{"at": e.at, "actor": e.actor, "event": e.event, "comment": e.comment}
                                  for e in events]}


class DecisionRequest(BaseModel):
    decision: str  # approve | reject | request_changes
    comment: str | None = Field(default=None, max_length=1000)


@router.post("/{approval_id}/decision")
def decide(approval_id: int, body: DecisionRequest, db: Session = Depends(get_db),
           who: Principal = Depends(get_principal)):
    try:
        return _out(service.decide(db, who, approval_id, body.decision, body.comment))
    except ApprovalError as e:
        raise _http(e) from e


class ResubmitRequest(BaseModel):
    args: dict


@router.post("/{approval_id}/resubmit")
def resubmit(approval_id: int, body: ResubmitRequest, db: Session = Depends(get_db),
             who: Principal = Depends(get_principal)):
    try:
        res = service.resubmit(db, who, approval_id, body.args)
    except ApprovalError as e:
        raise _http(e) from e
    return _out(res.approval)
