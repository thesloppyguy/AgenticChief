"""The only consequential operations the platform can perform on someone's behalf.

An action is declared here with its risk class, argument schema and executor. The executor is only ever
called by approvals.service after a human approval; nothing else (including the Copilot) imports it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import service as asset_service
from app.assets.definitions import MODELS as ASSET_MODELS
from app.core.security import Principal
from app.db.models import (
    ApprovalRequest,
    Asset,
    JobSchedule,
    OutboundMessage,
    Person,
    ReportSnapshot,
    ScorecardConfigVersion,
    Watch,
    WorkflowRun,
)
from app.kpi_registry.seed import KPIS
from app.reports.integrity import canonical_hash
from app.scheduler import cadence as cad
from app.scorecard_config import service as config_service
from app.scorecard_config.rules import ScorecardRules
from app.services.scorecard import active_config, build_scorecard

PERIOD_RE = r"^\d{4}-(0[1-9]|1[0-2])$"
_KPI_KEYS = {k.key for k in KPIS}


class Risk(StrEnum):
    READ = "read"  # runs without approval
    INTERNAL_WRITE = "internal_write"  # changes our own records
    EXTERNAL_MESSAGE = "external_message"  # reaches a person outside the platform
    DESTRUCTIVE = "destructive"  # denied by default


@dataclass(frozen=True)
class ActionDef:
    key: str
    risk: Risk
    description: str
    args_model: type[BaseModel]
    summarize: Callable[[BaseModel], str]
    targets: Callable[[BaseModel], list[str]]  # company codes the action touches (for scope + bulk checks)
    execute: Callable[[Session, ApprovalRequest, BaseModel, Principal], dict]
    group_wide_only: bool = False  # needs group-wide scope from both requester and approver
    # Rejects a request that can never succeed (raise ValueError) before anyone is asked to approve it.
    precheck: Callable[[Session, Principal, BaseModel], dict | None] | None = None


# --- people / outbound helpers -----------------------------------------------------------------

def _people_by_ids(db: Session, ids: list[int]) -> list[Person]:
    if not ids:
        return []
    return list(db.scalars(select(Person).where(Person.id.in_(ids))))


def _people_by_emails(db: Session, emails: list[str]) -> list[Person]:
    cleaned = sorted({e.strip().lower() for e in emails if e and e.strip()})
    if not cleaned:
        return []
    rows = list(db.scalars(select(Person).where(Person.email != "")))
    return [p for p in rows if (p.email or "").strip().lower() in cleaned]


def _hr_leads_for_codes(db: Session, codes: list[str]) -> list[Person]:
    """Prefer IC CHRO / Head of HR; fall back to any people-dept person for the code."""
    found: list[Person] = []
    for code in codes:
        rows = list(
            db.scalars(
                select(Person).where(Person.company_code == code).order_by(Person.id)
            )
        )
        prefer = [
            p
            for p in rows
            if any(k in (p.role or "").lower() for k in ("chro", "head of hr", "hr lead"))
        ]
        pick = prefer[0] if prefer else (rows[0] if rows else None)
        if pick:
            found.append(pick)
    return found


def _queue_message(
    db: Session,
    *,
    approval_id: int,
    channel: str,
    subject: str,
    body: str,
    person: Person | None = None,
    company_code: str | None = None,
    to_email: str | None = None,
) -> OutboundMessage:
    msg = OutboundMessage(
        approval_id=approval_id,
        channel=channel,
        company_code=company_code or (person.company_code if person else None),
        person_id=person.id if person else None,
        to_email=to_email or (person.email if person else None),
        subject=subject[:200],
        body=body,
        status="queued",
    )
    db.add(msg)
    return msg


def _arm_watch(
    db: Session,
    who: Principal,
    *,
    name: str,
    company_code: str | None,
    condition: dict,
    cadence: dict | None = None,
) -> int:
    """Create a watch + schedule without committing (approval executor owns the txn)."""
    from app.alerts import watches as watches_mod
    from app.db.models import Company

    c = watches_mod.parse(condition)
    watches_mod.check_known(db, c)
    company_id = None
    if company_code:
        company_id = db.scalar(select(Company.id).where(Company.code == company_code.upper()))
    clean = cad.validate(cadence or {"type": "daily", "time": "09:00"})
    w = Watch(
        user_id=who.user_id,
        name=name[:120],
        company_id=company_id,
        condition=c.model_dump(),
        enabled=True,
    )
    db.add(w)
    db.flush()
    s = JobSchedule(
        job="watch",
        name=f"watch: {name}"[:120],
        cadence=clean,
        params={"watch_id": w.id, "period": "current"},
        enabled=True,
        next_run_at=cad.next_after(clean, datetime.now(UTC)),
        created_by=who.user_id,
    )
    db.add(s)
    db.flush()
    w.schedule_id = s.id
    return w.id


# --- send_kpi_reminder ---------------------------------------------------------------------

class ReminderArgs(BaseModel):
    company_codes: list[str] = Field(min_length=1, max_length=200)
    period: str = Field(pattern=PERIOD_RE)
    kpi_key: str | None = None
    note: str = Field(default="", max_length=500)
    person_ids: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("company_codes")
    @classmethod
    def _norm(cls, v: list[str]) -> list[str]:
        return sorted({c.strip().upper() for c in v if c.strip()})

    @field_validator("kpi_key")
    @classmethod
    def _kpi(cls, v: str | None) -> str | None:
        if v is not None and v not in _KPI_KEYS:
            raise ValueError("unknown KPI")
        return v


def _reminder_text(a: ReminderArgs) -> tuple[str, str]:
    what = a.kpi_key.replace("_", " ") if a.kpi_key else "your HR scorecard KPIs"
    subject = f"Action needed: HR scorecard data for {a.period}"
    body = f"Please submit or confirm {what} for {a.period}."
    return subject, body + (f"\n\n{a.note}" if a.note else "")


def _send_reminders(db: Session, req: ApprovalRequest, a: ReminderArgs, approver: Principal) -> dict:
    del approver
    subject, body = _reminder_text(a)
    people = _people_by_ids(db, a.person_ids) if a.person_ids else _hr_leads_for_codes(db, a.company_codes)
    queued = 0
    recipients: list[dict] = []
    if people:
        for p in people:
            _queue_message(
                db,
                approval_id=req.id,
                channel="email",
                subject=subject,
                body=body,
                person=p,
                company_code=p.company_code,
            )
            queued += 1
            recipients.append({"person_id": p.id, "email": p.email, "name": p.full_name})
    else:
        for code in a.company_codes:
            _queue_message(
                db,
                approval_id=req.id,
                channel="email",
                subject=subject,
                body=body,
                company_code=code,
            )
            queued += 1
            recipients.append({"company_code": code})
    return {"queued": queued, "recipients": recipients}


# --- send_directive ------------------------------------------------------------------------

class DirectiveArgs(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    channel: str = Field(default="email")
    person_ids: list[int] = Field(default_factory=list, max_length=50)
    recipient_emails: list[str] = Field(default_factory=list, max_length=50)
    company_codes: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("channel")
    @classmethod
    def _ch(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("email", "teams"):
            raise ValueError("channel must be email or teams")
        return v

    @field_validator("company_codes")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        return sorted({c.strip().upper() for c in v if c.strip()})

    @model_validator(mode="after")
    def _need_targets(self) -> DirectiveArgs:
        if not self.person_ids and not self.recipient_emails and not self.company_codes:
            raise ValueError("provide person_ids, recipient_emails, or company_codes")
        return self


def _send_directive(db: Session, req: ApprovalRequest, a: DirectiveArgs, approver: Principal) -> dict:
    del approver
    people = _people_by_ids(db, a.person_ids)
    by_email = _people_by_emails(db, a.recipient_emails)
    seen = {p.id for p in people}
    for p in by_email:
        if p.id not in seen:
            people.append(p)
            seen.add(p.id)
    if a.company_codes and not people:
        people = _hr_leads_for_codes(db, a.company_codes)
    if not people and a.recipient_emails:
        # Queue to raw emails even if not on roster (demo-safe @example.com).
        queued = 0
        recipients = []
        for email in a.recipient_emails:
            _queue_message(
                db,
                approval_id=req.id,
                channel=a.channel,
                subject=a.subject,
                body=a.body,
                to_email=email,
                company_code=a.company_codes[0] if a.company_codes else None,
            )
            queued += 1
            recipients.append({"email": email})
        return {"queued": queued, "recipients": recipients}
    if not people:
        raise ValueError("no recipients resolved from roster")
    recipients = []
    for p in people:
        _queue_message(
            db,
            approval_id=req.id,
            channel=a.channel,
            subject=a.subject,
            body=a.body,
            person=p,
        )
        recipients.append({"person_id": p.id, "email": p.email, "name": p.full_name})
    return {"queued": len(recipients), "recipients": recipients}


# --- launch_capability_program -------------------------------------------------------------

class CapabilityArgs(BaseModel):
    program_key: str = Field(default="capability_green_h2", max_length=64)
    enrol_count: int = Field(default=40, ge=1, le=500)
    mobility_count: int = Field(default=12, ge=0, le=200)
    successor_count: int = Field(default=3, ge=0, le=50)
    mentor_count: int = Field(default=8, ge=0, le=100)
    recipient_emails: list[str] = Field(default_factory=list, max_length=50)
    person_ids: list[int] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="Capability programme approved", max_length=200)
    body: str = Field(default="", max_length=8000)
    channel: str = Field(default="email")
    company_codes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("channel")
    @classmethod
    def _ch(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("email", "teams"):
            raise ValueError("channel must be email or teams")
        return v

    @field_validator("company_codes")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        return sorted({c.strip().upper() for c in v if c.strip()})


def _launch_capability(db: Session, req: ApprovalRequest, a: CapabilityArgs, approver: Principal) -> dict:
    body = a.body.strip() or (
        f"Capability programme `{a.program_key}` approved. Enrol {a.enrol_count}, "
        f"open {a.mobility_count} mobility cases, {a.mentor_count} mentors, "
        f"fast-track {a.successor_count} successors."
    )
    directive = DirectiveArgs(
        subject=a.subject,
        body=body,
        channel=a.channel,
        person_ids=a.person_ids,
        recipient_emails=a.recipient_emails,
        company_codes=a.company_codes or ["LTTS", "LTIM"],
    )
    msg = _send_directive(db, req, directive, approver)
    watch_id = _arm_watch(
        db,
        approver,
        name=f"Capability 90-day · {a.program_key}",
        company_code=None,
        condition={"subject": "pillar", "pillar": "talent_management", "comparator": "below", "threshold": 85},
        cadence={"type": "weekly", "weekday": 0, "time": "09:00"},
    )
    return {
        **msg,
        "program_key": a.program_key,
        "enrol_count": a.enrol_count,
        "mobility_count": a.mobility_count,
        "watch_id": watch_id,
        "track": "/workflows",
    }


# --- launch_retention_corrective -----------------------------------------------------------

class RetentionArgs(BaseModel):
    program_key: str = Field(default="retention_semi", max_length=64)
    at_risk_count: int = Field(default=58, ge=1, le=5000)
    company_code: str = Field(default="LTIM", max_length=32)
    recipient_emails: list[str] = Field(default_factory=list, max_length=50)
    person_ids: list[int] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="Retention corrective approved", max_length=200)
    body: str = Field(default="", max_length=8000)
    channel: str = Field(default="email")
    company_codes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("channel")
    @classmethod
    def _ch(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("email", "teams"):
            raise ValueError("channel must be email or teams")
        return v

    @field_validator("company_code")
    @classmethod
    def _code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("company_codes")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        return sorted({c.strip().upper() for c in v if c.strip()})


def _launch_retention(db: Session, req: ApprovalRequest, a: RetentionArgs, approver: Principal) -> dict:
    body = a.body.strip() or (
        f"Retention corrective `{a.program_key}` approved for {a.company_code}. "
        f"Activate pathways for {a.at_risk_count} at-risk engineers; career + coaching, not pay."
    )
    codes = a.company_codes or [a.company_code]
    directive = DirectiveArgs(
        subject=a.subject,
        body=body,
        channel=a.channel,
        person_ids=a.person_ids,
        recipient_emails=a.recipient_emails,
        company_codes=codes,
    )
    msg = _send_directive(db, req, directive, approver)
    watch_id = _arm_watch(
        db,
        approver,
        name=f"Retention 90-day · {a.company_code}",
        company_code=a.company_code,
        condition={"subject": "pillar", "pillar": "retention", "comparator": "below", "threshold": 75},
        cadence={"type": "weekly", "weekday": 0, "time": "09:00"},
    )
    return {
        **msg,
        "program_key": a.program_key,
        "at_risk_count": a.at_risk_count,
        "company_code": a.company_code,
        "watch_id": watch_id,
        "track": "/workflows",
    }


# --- schedule_report -----------------------------------------------------------------------

class ScheduleReportArgs(BaseModel):
    report_key: str = Field(
        description="workforce_brief | monthly_review | scorecard_snapshot",
        max_length=64,
    )
    name: str = Field(default="", max_length=120)
    cadence: dict = Field(default_factory=lambda: {"type": "weekly", "weekday": 0, "time": "07:00"})
    period: str = Field(default="current")

    @field_validator("report_key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip().lower()
        allowed = {"workforce_brief", "monthly_review", "scorecard_snapshot"}
        if v not in allowed:
            raise ValueError(f"report_key must be one of {', '.join(sorted(allowed))}")
        return v


def _schedule_report(db: Session, req: ApprovalRequest, a: ScheduleReportArgs, approver: Principal) -> dict:
    del req
    clean = cad.validate(a.cadence)
    if a.report_key == "monthly_review":
        job, params = "monthly_review", {"period": a.period}
    elif a.report_key == "workforce_brief":
        # Prefer published weekly_workforce_brief workflow when present; else morning_brief job.
        asset = db.scalar(
            select(Asset).where(Asset.kind == "workflow", Asset.key == "weekly_workforce_brief")
        )
        if asset and asset.published_version is not None and not asset.deprecated:
            job, params = "workflow", {"period": a.period, "workflow_key": "weekly_workforce_brief"}
        else:
            job, params = "morning_brief", {}
    else:  # scorecard_snapshot — use morning_brief as periodic reminder surface
        job, params = "morning_brief", {}

    name = a.name.strip() or f"Scheduled {a.report_key}"
    s = JobSchedule(
        job=job,
        name=name[:120],
        cadence=clean,
        params=params,
        enabled=True,
        next_run_at=cad.next_after(clean, datetime.now(UTC)),
        created_by=approver.user_id,
    )
    db.add(s)
    db.flush()
    return {"schedule_id": s.id, "job": job, "name": s.name, "next_run_at": s.next_run_at.isoformat()}


# --- create_snapshot -----------------------------------------------------------------------

class SnapshotArgs(BaseModel):
    period: str = Field(pattern=PERIOD_RE)


def _create_snapshot(db: Session, req: ApprovalRequest, a: SnapshotArgs, approver: Principal) -> dict:
    del req
    payload = build_scorecard(db, approver, a.period)
    snap = ReportSnapshot(kind="scorecard", period=a.period, calc_version=active_config(db).version,
                          payload=payload, content_hash=canonical_hash(payload), created_by=approver.user_id)
    db.add(snap)
    db.flush()
    return {"snapshot_id": snap.id, "no_source_kpis": sorted(active_config(db).no_source)}


# --- publish_monthly_report ----------------------------------------------------------------

class PublishArgs(BaseModel):
    run_id: int = Field(gt=0)


def _precheck_publish(db: Session, who: Principal, a: PublishArgs) -> None:
    del who
    run = db.get(WorkflowRun, a.run_id)
    if run is None or run.workflow != "monthly_review":
        raise ValueError("unknown report run")
    if run.status != "succeeded" or not run.result:
        raise ValueError("only a completed report can be published")
    if db.scalar(select(ReportSnapshot.id).where(ReportSnapshot.run_id == a.run_id)):
        raise ValueError("this report has already been published")


def _publish(db: Session, req: ApprovalRequest, a: PublishArgs, approver: Principal) -> dict:
    del req
    run = db.get(WorkflowRun, a.run_id)
    snap = ReportSnapshot(kind="monthly_review", period=run.period, calc_version=run.result["meta"]["calc_version"],
                          payload=run.result, content_hash=canonical_hash(run.result), run_id=run.id,
                          created_by=approver.user_id)
    db.add(snap)
    db.flush()
    return {"snapshot_id": snap.id, "content_hash": snap.content_hash}


# --- publish_asset (workflow definitions) -------------------------------------------------------

class PublishAssetArgs(BaseModel):
    asset_id: int = Field(gt=0)
    version: int | None = Field(default=None, gt=0, description="defaults to the latest version")


def _precheck_publish_asset(db: Session, who: Principal, a: PublishAssetArgs) -> dict:
    del who
    asset = db.get(Asset, a.asset_id)
    if asset is None:
        raise ValueError("unknown workflow")
    if asset.kind != "workflow":
        raise ValueError("only workflow assets can be published")
    version = a.version or asset.version
    row = asset_service.version_row(db, asset, version)
    if row is None:
        raise ValueError("unknown version")
    if asset.deprecated:
        raise ValueError("a deprecated workflow cannot be published")
    if not row.validated:
        raise ValueError("that version has not passed validation")
    if asset.published_version == version:
        raise ValueError("that version is already published")
    d = ASSET_MODELS[asset.kind](**row.definition)
    return {"kind": asset.kind, "key": asset.key, "name": asset.name, "version": version,
            "previous_published_version": asset.published_version,
            "tools": getattr(d, "tools", []),
            "title": getattr(d, "title", asset.name),
            "is_rollback": asset.published_version is not None and version < asset.published_version}


def _publish_asset(db: Session, req: ApprovalRequest, a: PublishAssetArgs, approver: Principal) -> dict:
    del req
    asset = db.get(Asset, a.asset_id)
    version = a.version or asset.version
    asset_service.publish_version(db, approver, asset, version)
    return {"kind": asset.kind, "key": asset.key, "published_version": version}


# --- activate_scorecard_config ---------------------------------------------------------------

class ActivateConfigArgs(BaseModel):
    version: int = Field(gt=1)


def _precheck_activate_config(db: Session, who: Principal, a: ActivateConfigArgs) -> dict:
    del who
    row = db.scalar(select(ScorecardConfigVersion).where(ScorecardConfigVersion.version == a.version))
    if row is None:
        raise ValueError("unknown scorecard config version")
    if row.status != "draft":
        raise ValueError(f"only a draft can be activated (this one is {row.status})")
    try:
        new = ScorecardRules(**row.rules)
    except ValueError as e:
        raise ValueError("the stored rules are no longer valid") from e
    old, old_version = config_service.active(db)
    changes = config_service.diff(old, new)
    if not changes:
        raise ValueError("this draft changes nothing compared with the active rules")
    return {"activating_version": a.version, "replacing_version": old_version, "note": row.note, "changes": changes,
            "effect": "Every score, status and report from now on uses these rules. Published snapshots are unchanged."}


def _activate_config(db: Session, req: ApprovalRequest, a: ActivateConfigArgs, approver: Principal) -> dict:
    del req
    config_service.activate(db, approver, a.version)
    return {"active_version": a.version}


ACTIONS: dict[str, ActionDef] = {
    d.key: d
    for d in (
        ActionDef(
            "send_kpi_reminder", Risk.EXTERNAL_MESSAGE,
            "Ask companies' HR leads to submit or confirm KPI data for a period.",
            ReminderArgs,
            lambda a: f"Remind {len(a.company_codes)} company(ies) about "
                      f"{a.kpi_key or 'KPI data'} for {a.period}",
            lambda a: list(a.company_codes), _send_reminders),
        ActionDef(
            "send_directive", Risk.EXTERNAL_MESSAGE,
            "Send a company-wide decision or direction to named People (email/Teams queue).",
            DirectiveArgs,
            lambda a: (
                f"Directive to "
                f"{(len(a.person_ids) + len(a.recipient_emails)) or len(a.company_codes)} "
                f"recipient(s): {a.subject[:60]}"
            ),
            lambda a: list(a.company_codes), _send_directive),
        ActionDef(
            "launch_capability_program", Risk.EXTERNAL_MESSAGE,
            "Approve capability build: message L&D/IC HR and arm a 90-day talent-management watch.",
            CapabilityArgs,
            lambda a: f"Launch capability `{a.program_key}` ({a.enrol_count} enrolments)",
            lambda a: list(a.company_codes), _launch_capability, group_wide_only=True),
        ActionDef(
            "launch_retention_corrective", Risk.EXTERNAL_MESSAGE,
            "Approve retention corrective for an IC: message HR leads and arm a 90-day retention watch.",
            RetentionArgs,
            lambda a: f"Retention corrective `{a.program_key}` for {a.company_code} "
                      f"({a.at_risk_count} at risk)",
            lambda a: list(a.company_codes) or [a.company_code], _launch_retention, group_wide_only=True),
        ActionDef(
            "schedule_report", Risk.INTERNAL_WRITE,
            "Schedule recurring workforce brief, monthly review, or scorecard reminder.",
            ScheduleReportArgs,
            lambda a: f"Schedule {a.report_key} ({a.cadence.get('type', 'custom')})",
            lambda a: [], _schedule_report, group_wide_only=True),
        ActionDef(
            "create_snapshot", Risk.INTERNAL_WRITE,
            "Save an immutable Group scorecard snapshot for a period.",
            SnapshotArgs, lambda a: f"Save scorecard snapshot for {a.period}",
            lambda a: [], _create_snapshot, group_wide_only=True),
        ActionDef(
            "publish_monthly_report", Risk.INTERNAL_WRITE,
            "Publish a completed monthly review as an immutable, hash-verified snapshot.",
            PublishArgs, lambda a: f"Publish monthly review (run #{a.run_id})",
            lambda a: [], _publish, group_wide_only=True, precheck=_precheck_publish),
        ActionDef(
            "publish_asset", Risk.INTERNAL_WRITE,
            "Make a validated workflow version available (or roll back to an older one).",
            PublishAssetArgs, lambda a: f"Publish workflow #{a.asset_id} v{a.version or 'latest'}",
            lambda a: [], _publish_asset, group_wide_only=True, precheck=_precheck_publish_asset),
        ActionDef(
            "activate_scorecard_config", Risk.INTERNAL_WRITE,
            "Make a drafted set of scoring rules the active rules for every score and report.",
            ActivateConfigArgs, lambda a: f"Activate scorecard rules v{a.version}",
            lambda a: [], _activate_config, group_wide_only=True, precheck=_precheck_activate_config),
    )
}
