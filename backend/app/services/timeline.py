"""One time-ordered feed of everything the platform did: Copilot tool calls, delegations, capability
calls, workflow steps, ingestion runs, approval decisions, scheduled job runs and watch firings.

Merged here rather than in the client because each source has its own scoping rule, and six of them
re-implemented in TypeScript is six chances to leak. Every source is filtered for `who` before it is
merged, so the merge itself needs no further checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import store as alert_store
from app.core.security import Principal, Role
from app.db.models import (
    Alert,
    ApprovalEvent,
    ApprovalRequest,
    AuditEvent,
    IngestionRun,
    JobSchedule,
    WorkflowEvent,
    WorkflowRun,
)

MAX_LIMIT = 200
SOURCES = ("audit", "workflow", "ingestion", "approval", "schedule", "watch")

# audit_event.action -> the timeline kind it becomes. Anything else is compliance detail, not activity.
AUDIT_KINDS = {
    "copilot_tool": "tool",
    "copilot_capability_call": "capability",
    "copilot_delegate": "delegate",
}

_STEP_STATUS = {"started": "running", "done": "ok", "failed": "failed", "skipped": "skipped"}
_RUN_STATUS = {"success": "ok", "partial": "failed", "failed": "failed", "running": "running"}
_APPROVAL_STATUS = {"submitted": "pending", "approved": "ok", "executed": "ok", "rejected": "failed",
                    "denied": "failed", "failed": "failed", "changes_requested": "pending"}


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Cursor:
    """Where the previous page stopped. A bare timestamp is not enough: two sources can share one,
    and an `at < cursor` filter would silently drop whichever sorted second.

    Encoded as microseconds since the epoch, not isoformat: isoformat ends in "+00:00", and a bare
    "+" in a query string decodes to a space, so the cursor would never parse.
    """

    at: datetime
    source: str
    pk: int

    def encode(self) -> str:
        return f"{int((self.at - EPOCH) // timedelta(microseconds=1))}.{self.source}.{self.pk}"

    @classmethod
    def decode(cls, raw: str) -> Cursor | None:
        try:
            micros, source, pk = raw.split(".", 2)
            return cls(EPOCH + timedelta(microseconds=int(micros)), source, int(pk))
        except (ValueError, AttributeError):
            return None  # a malformed cursor starts from the top rather than erroring


def _key(item: dict) -> tuple[datetime, str, int]:
    return item["at"], item["source"], item["_pk"]


def _item(source: str, pk: int, at: datetime, kind: str, actor: str, title: str, status: str,
          entity: str | None = None, company_id: int | None = None, period: str | None = None,
          ref: dict | None = None, detail: dict | None = None) -> dict:
    return {"id": f"{source}:{pk}", "_pk": pk, "source": source, "at": at, "kind": kind, "actor": actor,
            "title": title, "status": status, "entity": entity, "company_id": company_id,
            "period": period, "ref": ref, "detail": detail}


def _audit(db: Session, who: Principal, upto: datetime | None, limit: int) -> list[dict]:
    """Admins see everyone's; everyone else sees only their own. One user's Copilot activity is
    never shown to another, whatever their company scope."""
    q = select(AuditEvent).where(AuditEvent.action.in_(AUDIT_KINDS)).order_by(AuditEvent.at.desc())
    if who.role is not Role.ADMIN:
        q = q.where(AuditEvent.actor == who.user_id)
    if upto is not None:
        q = q.where(AuditEvent.at <= upto)
    rows = db.scalars(q.limit(limit))
    out = []
    for r in rows:
        kind = AUDIT_KINDS[r.action]
        verb = {"tool": "Used tool", "capability": "Called capability", "delegate": "Delegated to"}[kind]
        out.append(_item("audit", r.id, r.at, kind, r.actor, f"{verb} {r.target}", "ok", detail=r.detail))
    return out


def _workflow(db: Session, who: Principal, upto: datetime | None, limit: int) -> list[dict]:
    if who.company_ids is not None:  # workflow runs are group-wide (see app/api/workflows.py)
        return []
    q = (select(WorkflowEvent, WorkflowRun)
         .join(WorkflowRun, WorkflowRun.id == WorkflowEvent.run_id)
         .order_by(WorkflowEvent.at.desc()))
    if upto is not None:
        q = q.where(WorkflowEvent.at <= upto)
    return [
        _item("workflow", e.id, e.at, "workflow_step", run.requested_by, e.message,
              _STEP_STATUS.get(e.status, "ok"), entity=run.workflow, period=run.period,
              ref={"type": "workflow_run", "id": run.id}, detail=e.data)
        for e, run in db.execute(q.limit(limit)).all()
    ]


def _ingestion(db: Session, who: Principal, upto: datetime | None, limit: int) -> list[dict]:
    if who.company_ids is not None:
        return []
    q = select(IngestionRun).order_by(IngestionRun.started_at.desc())
    if upto is not None:
        q = q.where(IngestionRun.started_at <= upto)
    return [
        _item("ingestion", r.id, r.started_at, "ingestion_run", "system",
              f"Ingested {r.source} ({r.mode}): {r.records_written} records, "
              f"{r.companies_ok} ok / {r.companies_failed} failed",
              _RUN_STATUS.get(r.status, "running"), entity=r.source, period=r.period,
              ref={"type": "ingestion_run", "id": r.id},
              detail={"errors": r.errors} if r.errors else None)
        for r in db.scalars(q.limit(limit))
    ]


def _approval(db: Session, who: Principal, upto: datetime | None, limit: int) -> list[dict]:
    """Same rule as approvals.service.list_for: admins see all, everyone else only their own."""
    q = (select(ApprovalEvent, ApprovalRequest)
         .join(ApprovalRequest, ApprovalRequest.id == ApprovalEvent.approval_id)
         .order_by(ApprovalEvent.at.desc()))
    if who.role is not Role.ADMIN:
        q = q.where(ApprovalRequest.requested_by == who.user_id)
    if upto is not None:
        q = q.where(ApprovalEvent.at <= upto)
    return [
        _item("approval", e.id, e.at, "approval", e.actor, f"{e.event.replace('_', ' ').capitalize()}: {req.summary}",
              _APPROVAL_STATUS.get(e.event, "pending"), entity=req.action,
              ref={"type": "approval", "id": req.id},
              detail={"comment": e.comment, "via": req.via} if e.comment or req.via else None)
        for e, req in db.execute(q.limit(limit)).all()
    ]


def _schedule(db: Session, who: Principal, upto: datetime | None, limit: int) -> list[dict]:
    """Last run only: JobSchedule keeps no history. A per-run history would need its own table."""
    if who.role is not Role.ADMIN or who.company_ids is not None:
        return []
    q = select(JobSchedule).where(JobSchedule.last_run_at.is_not(None)).order_by(JobSchedule.last_run_at.desc())
    if upto is not None:
        q = q.where(JobSchedule.last_run_at <= upto)
    return [
        _item("schedule", s.id, s.last_run_at, "job_run", "scheduler", f"{s.name}: {s.last_detail or s.last_status}",
              "ok" if s.last_status == "success" else "failed", entity=s.job,
              ref={"type": "schedule", "id": s.id})
        for s in db.scalars(q.limit(limit))
    ]


def _watch(db: Session, who: Principal, upto: datetime | None, limit: int) -> list[dict]:
    q = alert_store._visible(who).where(Alert.kind == "watch_fired").order_by(Alert.created_at.desc())
    if upto is not None:
        q = q.where(Alert.created_at <= upto)
    return [
        _item("watch", a.id, a.created_at, "watch_fired", a.audience_user_id or "system", a.title, "failed",
              entity=a.entity, company_id=a.company_id, period=a.period,
              ref={"type": "alert", "id": a.id}, detail=a.detail)
        for a in db.scalars(q.limit(limit))
    ]


_FETCHERS = {"audit": _audit, "workflow": _workflow, "ingestion": _ingestion,
             "approval": _approval, "schedule": _schedule, "watch": _watch}


def fetch(db: Session, who: Principal, limit: int = 50, cursor: str | None = None,
          kinds: list[str] | None = None, company_id: int | None = None) -> dict:
    """One page of the merged feed, newest first. Each source is over-fetched by one row so the
    merge can tell a full page from the last one."""
    limit = max(1, min(limit, MAX_LIMIT))
    cur = Cursor.decode(cursor) if cursor else None
    items: list[dict] = []
    saturated = False
    for fetcher in _FETCHERS.values():
        got = fetcher(db, who, cur.at if cur else None, limit + 1)
        saturated = saturated or len(got) > limit  # this source has more behind it
        items += got

    items.sort(key=_key, reverse=True)
    if cur is not None:  # drop everything the previous page already returned, ties included
        items = [i for i in items if _key(i) < (cur.at, cur.source, cur.pk)]
    unfiltered = items
    if kinds:
        items = [i for i in items if i["kind"] in kinds]
    if company_id is not None:
        items = [i for i in items if i["company_id"] == company_id]

    page = items[:limit]
    more = len(items) > limit or saturated
    # A filter can empty a page while rows remain behind it, so fall back to the last unfiltered
    # row's key: the client keeps paging instead of concluding the feed ended.
    anchor = page[-1] if page else (unfiltered[:limit][-1] if unfiltered and more else None)
    next_cursor = Cursor(*_key(anchor)).encode() if anchor is not None and more else None
    for i in page:
        i.pop("_pk", None)
    return {"items": page, "next_cursor": next_cursor}
