"""Approval workflow. Everything that executes an action goes through execute_approved()."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.core.config import settings
from app.core.security import Principal, Role
from app.db.models import ApprovalEvent, ApprovalRequest
from app.services.scorecard import visible_companies

from .actions import ACTIONS, ActionDef, Risk
from .policy import Verdict, evaluate


class ApprovalError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class SubmitResult:
    verdict: str  # require_approval | allow | deny
    reason: str
    approval: ApprovalRequest | None


def _event(db: Session, approval_id: int, actor: str, event: str, comment: str | None = None) -> None:
    db.add(ApprovalEvent(approval_id=approval_id, actor=actor, event=event, comment=comment))


def _parse(action: ActionDef, raw_args: dict[str, Any]):
    try:
        return action.args_model(**raw_args)
    except (ValidationError, TypeError) as e:
        locs = sorted({".".join(map(str, err["loc"])) for err in e.errors()}) if isinstance(e, ValidationError) else []
        raise ApprovalError(422, "invalid arguments" + (f": {', '.join(locs)}" if locs else "")) from e


def _precheck(db: Session, who: Principal, action: ActionDef, args) -> dict:
    """Rejects a request that can never succeed; returns supporting context for the approver to see."""
    if not action.precheck:
        return {}
    try:
        return action.precheck(db, who, args) or {}
    except ValueError as e:
        raise ApprovalError(422, str(e)) from e


def submit(db: Session, who: Principal, action_key: str, raw_args: dict, via: str = "api",
           session_id: int | None = None, context: dict | None = None) -> SubmitResult:
    action = ACTIONS.get(action_key)
    if action is None:
        raise ApprovalError(404, "unknown action")
    args = _parse(action, raw_args)
    context = {**(context or {}), **_precheck(db, who, action, args)}
    visible = {c.code for c in visible_companies(db, who)}
    decision = evaluate(action, action.targets(args), visible, who)

    status = {Verdict.DENY: "denied", Verdict.REQUIRE_APPROVAL: "pending", Verdict.ALLOW: "approved"}[decision.verdict]
    req = ApprovalRequest(action=action.key, risk=action.risk.value, summary=action.summarize(args)[:300],
                          args=args.model_dump(mode="json"), context=context, requested_by=who.user_id,
                          via=via, session_id=session_id, status=status)
    db.add(req)
    db.flush()
    _event(db, req.id, who.user_id, "submitted")
    if decision.verdict is Verdict.DENY:
        _event(db, req.id, "policy", "denied", decision.reason)
        req.decision_comment = decision.reason
    audit(db, who, f"approval_{status}", f"{action.key}#{req.id}", {"via": via})
    if decision.verdict is Verdict.ALLOW:  # only READ-risk actions; none registered yet
        execute_approved(db, req, who)
    db.commit()
    return SubmitResult(decision.verdict.value, decision.reason, req)


def execute_approved(db: Session, req: ApprovalRequest, approver: Principal) -> None:
    """The single place an action's executor is called. Refuses anything not approved."""
    if req.status not in ("approved",):
        raise ApprovalError(409, "only approved requests can be executed")
    action = ACTIONS[req.action]
    args = action.args_model(**req.args)
    try:
        with db.begin_nested():  # a failed executor leaves no partial writes behind
            result = action.execute(db, req, args, approver)
        req.status, req.result = "executed", result
        _event(db, req.id, approver.user_id, "executed")
    except Exception as e:  # noqa: BLE001 - recorded by type only; never echo details
        req.status, req.result = "failed", {"error": type(e).__name__}
        _event(db, req.id, approver.user_id, "failed", type(e).__name__)


def get_visible(db: Session, who: Principal, approval_id: int) -> ApprovalRequest:
    req = db.get(ApprovalRequest, approval_id)
    if req is None or not (who.role is Role.ADMIN or req.requested_by == who.user_id):
        raise ApprovalError(404, "approval not found")
    return req


def decide(db: Session, who: Principal, approval_id: int, decision: str, comment: str | None) -> ApprovalRequest:
    if who.role is not Role.ADMIN:
        raise ApprovalError(403, "only admins can decide approvals")
    req = db.get(ApprovalRequest, approval_id)
    if req is None:
        raise ApprovalError(404, "approval not found")
    if decision not in ("approve", "reject", "request_changes"):
        raise ApprovalError(422, "unknown decision")
    if req.status != "pending":  # cheap early check; the atomic claim below is what actually guards races
        raise ApprovalError(409, "this request is no longer pending")
    if decision != "approve" and not (comment or "").strip():
        raise ApprovalError(422, "a comment is required to reject or request changes")
    if req.requested_by == who.user_id and not settings.approval_allow_self_approval:
        raise ApprovalError(403, "you cannot decide your own request")

    action = ACTIONS[req.action]
    if decision == "approve":
        args = action.args_model(**req.args)
        visible = {c.code for c in visible_companies(db, who)}
        if (action.group_wide_only and who.company_ids is not None) or any(t not in visible for t in action.targets(args)):
            raise ApprovalError(403, "your scope does not cover this request")
        if action.risk is Risk.DESTRUCTIVE:
            raise ApprovalError(403, "destructive actions cannot be approved")

    new_status = {"approve": "approved", "reject": "rejected", "request_changes": "changes_requested"}[decision]
    # Atomic claim: of two concurrent deciders only one flips the row from pending.
    claimed = db.execute(update(ApprovalRequest)
                         .where(ApprovalRequest.id == approval_id, ApprovalRequest.status == "pending")
                         .values(status=new_status, decided_by=who.user_id, decided_at=datetime.now(UTC),
                                 decision_comment=comment)).rowcount
    if claimed != 1:
        db.rollback()
        raise ApprovalError(409, "this request is no longer pending")
    db.refresh(req)
    _event(db, approval_id, who.user_id, new_status, comment)
    audit(db, who, f"approval_{new_status}", f"{req.action}#{approval_id}")
    if decision == "approve":
        execute_approved(db, req, who)
    db.commit()
    return req


def resubmit(db: Session, who: Principal, approval_id: int, raw_args: dict) -> SubmitResult:
    req = get_visible(db, who, approval_id)
    if req.requested_by != who.user_id:
        raise ApprovalError(403, "only the requester can resubmit")
    if req.status != "changes_requested":
        raise ApprovalError(409, "this request is not awaiting changes")
    action = ACTIONS[req.action]
    args = _parse(action, raw_args)
    extra = _precheck(db, who, action, args)
    visible = {c.code for c in visible_companies(db, who)}
    decision = evaluate(action, action.targets(args), visible, who)
    if decision.verdict is Verdict.DENY:
        raise ApprovalError(403, decision.reason)
    req.args, req.summary = args.model_dump(mode="json"), action.summarize(args)[:300]
    req.context = {**(req.context or {}), **extra}
    req.status, req.decided_by, req.decided_at, req.decision_comment = "pending", None, None, None
    _event(db, req.id, who.user_id, "resubmitted")
    audit(db, who, "approval_resubmitted", f"{action.key}#{req.id}")
    db.commit()
    return SubmitResult(decision.verdict.value, decision.reason, req)


def list_for(db: Session, who: Principal, status: str | None = None) -> list[ApprovalRequest]:
    q = select(ApprovalRequest).order_by(ApprovalRequest.id.desc()).limit(200)
    if who.role is not Role.ADMIN:
        q = q.where(ApprovalRequest.requested_by == who.user_id)
    if status:
        q = q.where(ApprovalRequest.status == status)
    return list(db.scalars(q))


def pending_count(db: Session, who: Principal) -> int:
    """Pending requests this user could act on (admins only; never their own under four-eyes)."""
    if who.role is not Role.ADMIN:
        return 0
    q = select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "pending")
    if not settings.approval_allow_self_approval:
        q = q.where(ApprovalRequest.requested_by != who.user_id)
    return db.scalar(q) or 0
