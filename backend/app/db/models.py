from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .session import Base
from .types import UtcDateTime


class Company(Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)


class Person(Base):
    """OE-inspired roster entry. company_code None = Group-level (e.g. Group CHRO)."""

    __tablename__ = "person"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), default="")
    company_code: Mapped[str | None] = mapped_column(String(32), index=True)  # None = Group
    is_principal: Mapped[bool] = mapped_column(default=False)
    authority_scope: Mapped[list | None] = mapped_column(JSON, default=list)
    department_slugs: Mapped[list | None] = mapped_column(JSON, default=list)
    preferred_channel: Mapped[str] = mapped_column(String(24), default="any")
    response_sla_hours: Mapped[int | None] = mapped_column(Integer)


class Department(Base):
    """Org unit with optional specialist mapping and charter."""

    __tablename__ = "department"
    __table_args__ = (UniqueConstraint("company_code", "slug", name="uq_department_company_slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(120))
    company_code: Mapped[str | None] = mapped_column(String(32), index=True)  # None = Group
    specialist_key: Mapped[str | None] = mapped_column(String(32))
    head_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    authority_level: Mapped[str] = mapped_column(String(24), default="propose_only")
    charter: Mapped[dict | None] = mapped_column(JSON)
    headcount: Mapped[int | None] = mapped_column(Integer)


class Goal(Base):
    """Department OKR / key result, optionally linked to a scorecard pillar."""

    __tablename__ = "goal"
    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    period_type: Mapped[str] = mapped_column(String(16), default="quarter")  # quarter | ongoing
    period_value: Mapped[str] = mapped_column(String(32), default="")
    key_result: Mapped[str] = mapped_column(String(400))
    target: Mapped[str] = mapped_column(String(120), default="")
    current: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="on_track")  # on_track | at_risk | off_track
    pillar_key: Mapped[str | None] = mapped_column(String(48))


class KpiRecord(Base):
    """One validated value per (company, kpi, period). period = 'YYYY-MM'."""

    __tablename__ = "kpi_record"
    __table_args__ = (UniqueConstraint("company_id", "kpi_key", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    kpi_key: Mapped[str] = mapped_column(String(64))
    period: Mapped[str] = mapped_column(String(7), index=True)
    achievement: Mapped[float | None] = mapped_column(Float)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))  # system name or "manual"
    detail: Mapped[dict | None] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class ManualInputHistory(Base):
    __tablename__ = "manual_input_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    kpi_key: Mapped[str] = mapped_column(String(64))
    period: Mapped[str] = mapped_column(String(7))
    user_id: Mapped[str] = mapped_column(String(128))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Indexed for the activity timeline, which orders by `at` and filters by `actor`.
    at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now(), index=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[dict | None] = mapped_column(JSON)


class ReportSnapshot(Base):
    """Immutable published report. content_hash is sha256 of the canonical payload, so tampering shows."""

    __tablename__ = "report_snapshot"
    __table_args__ = (UniqueConstraint("run_id", name="uq_report_snapshot_run_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), default="scorecard", server_default="scorecard")
    period: Mapped[str] = mapped_column(String(7), index=True)
    calc_version: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_run.id", name="fk_report_snapshot_run_id"))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class ImmutableRecordError(RuntimeError):
    pass


@event.listens_for(ReportSnapshot, "before_update")
@event.listens_for(ReportSnapshot, "before_delete")
def _snapshots_are_immutable(mapper, connection, target):
    raise ImmutableRecordError("published report snapshots cannot be changed or deleted")


class WorkflowRun(Base):
    """A persisted workflow run. `state` holds each finished step's output, so a run interrupted by a
    restart resumes after its last completed step instead of starting over."""

    __tablename__ = "workflow_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(48), index=True)
    period: Mapped[str] = mapped_column(String(7))
    status: Mapped[str] = mapped_column(String(16), index=True)  # queued|running|succeeded|failed|interrupted
    params: Mapped[dict | None] = mapped_column(JSON)
    requested_by: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(200))
    heartbeat_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class WorkflowEvent(Base):
    __tablename__ = "workflow_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_run.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    step: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(12))  # started | done | skipped | failed
    message: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict | None] = mapped_column(JSON)


class ChatSession(Base):
    __tablename__ = "chat_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New session")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_session.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String)
    tool_calls: Mapped[list | None] = mapped_column(JSON)
    artifacts: Mapped[list | None] = mapped_column(JSON)  # chart/table payloads for chat UI
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class IngestionRun(Base):
    """One source's pull for one period. Drives data-freshness and integration-health views."""

    __tablename__ = "ingestion_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # live | stub
    period: Mapped[str] = mapped_column(String(7))
    status: Mapped[str] = mapped_column(String(16))  # running | success | partial | failed
    companies_ok: Mapped[int] = mapped_column(Integer, default=0)
    companies_failed: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(JSON)  # exception type names only, never raw payloads
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class ApprovalRequest(Base):
    """A proposed consequential action awaiting a human decision. The backend, not the model or UI,
    decides what may run: see app/approvals."""

    __tablename__ = "approval_request"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    risk: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(String(300))
    args: Mapped[dict] = mapped_column(JSON)
    context: Mapped[dict | None] = mapped_column(JSON)  # supporting context, e.g. the model's reason
    requested_by: Mapped[str] = mapped_column(String(128), index=True)
    via: Mapped[str] = mapped_column(String(16))  # api | copilot
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_session.id"))
    # pending | changes_requested | approved | rejected | denied | executed | failed
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    decision_comment: Mapped[str | None] = mapped_column(String(1000))
    result: Mapped[dict | None] = mapped_column(JSON)


class ApprovalEvent(Base):
    """Append-only decision history."""

    __tablename__ = "approval_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int] = mapped_column(ForeignKey("approval_request.id"), index=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(128))
    event: Mapped[str] = mapped_column(String(24))
    comment: Mapped[str | None] = mapped_column(String(1000))


class OutboundMessage(Base):
    """Approved messages waiting for a real delivery channel (email/chat integration not built yet)."""

    __tablename__ = "outbound_message"
    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval_request.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    company_code: Mapped[str | None] = mapped_column(String(32))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"), index=True)
    to_email: Mapped[str | None] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class Alert(Base):
    __tablename__ = "alert"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # status_red | ingestion_failed | watch_fired
    severity: Mapped[str] = mapped_column(String(12))  # low | medium | high | urgent
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), index=True)  # None = group-wide
    entity: Mapped[str] = mapped_column(String(64))  # company code, "group", or a source name
    period: Mapped[str] = mapped_column(String(7))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[dict | None] = mapped_column(JSON)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    # None = anyone whose scope covers it. Set for a private alert (a user's own watch), so one
    # person's watch does not notify everyone who happens to see that company.
    audience_user_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class AlertRead(Base):
    __tablename__ = "alert_read"
    __table_args__ = (UniqueConstraint("alert_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alert.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)


class ScorecardConfigVersion(Base):
    """A version of the scoring rules. Exactly one is active; with none stored, the built-in defaults
    (version 1) apply. Activation needs a second admin's approval."""

    __tablename__ = "scorecard_config_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(12), index=True)  # draft | active | superseded
    rules: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    activated_by: Mapped[str | None] = mapped_column(String(128))
    activated_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class Pin(Base):
    """A user's bookmark: a report, snapshot, session, skill, agent or saved dashboard view."""

    __tablename__ = "pin"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_pin"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # run | snapshot | session | skill | agent | view
    ref: Mapped[str] = mapped_column(String(300))  # an id, a key, or (for views) an in-app path
    label: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class Document(Base):
    """Reference material the Copilot can search. Its text is data to cite, never instructions."""

    __tablename__ = "document"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(24), default="general")
    builtin: Mapped[bool] = mapped_column(default=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), index=True)
    ord: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String)


class Asset(Base):
    """Versioned workflow definition (kind='workflow'). Skills and agents live as Markdown/code
    registries (OpenExecutive port), not in this table."""

    __tablename__ = "asset"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_asset_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)  # workflow
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    validated_version: Mapped[int | None] = mapped_column(Integer)
    published_version: Mapped[int | None] = mapped_column(Integer)
    deprecated: Mapped[bool] = mapped_column(default=False)
    builtin: Mapped[bool] = mapped_column(default=False)
    lifecycle: Mapped[str] = mapped_column(String(16), index=True)
    validation: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class AssetVersion(Base):
    __tablename__ = "asset_version"
    __table_args__ = (UniqueConstraint("asset_id", "version", name="uq_asset_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)
    validated: Mapped[bool] = mapped_column(default=False)
    eval_passed: Mapped[bool | None] = mapped_column()  # None = never evaluated
    eval_results: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class JobSchedule(Base):
    """A recurring job run by the in-process scheduler (single instance: SQLite is single-writer)."""

    __tablename__ = "job_schedule"
    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(32))  # ingest | monthly_review
    name: Mapped[str] = mapped_column(String(120))
    cadence: Mapped[dict] = mapped_column(JSON)
    params: Mapped[dict | None] = mapped_column(JSON)  # e.g. {"period": "previous", "sources": ["successfactors"]}
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_status: Mapped[str | None] = mapped_column(String(16))  # success | failed
    last_detail: Mapped[str | None] = mapped_column(String(200))
    claimed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())  # set while a run is in flight
    created_by: Mapped[str] = mapped_column(String(128))


class Watch(Base):
    """A user-defined condition checked on a cadence. `condition` is validated by app.alerts.watches;
    the cadence lives on the paired JobSchedule, so watches reuse the scheduler's claiming and
    crash recovery rather than growing their own."""

    __tablename__ = "watch"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)  # the owner; alerts go only to them
    name: Mapped[str] = mapped_column(String(120))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), index=True)  # None = group
    condition: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(default=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("job_schedule.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class MockCompanyData(Base):
    """One company's HR profile as 'known' by the mock source systems, generated by Claude on first need."""

    __tablename__ = "mock_company_data"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_code: Mapped[str] = mapped_column(String(32), unique=True)
    archetype: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(12))  # ai | fallback
    model: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class UserPrefs(Base):
    """Per-user settings: alert filtering, quiet hours, and whether the Copilot may remember."""

    __tablename__ = "user_prefs"
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    min_severity: Mapped[str] = mapped_column(String(12), default="low")
    muted_kinds: Mapped[list] = mapped_column(JSON, default=list)
    quiet_start: Mapped[str | None] = mapped_column(String(5))  # "HH:MM" in `tz`
    quiet_end: Mapped[str | None] = mapped_column(String(5))
    tz: Mapped[str] = mapped_column(String(64), default="UTC")
    memory_enabled: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class UserMemory(Base):
    """Something the Copilot remembers about a user's earlier sessions. Private to that user."""

    __tablename__ = "user_memory"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # decision | initiative | advice
    domain: Mapped[str] = mapped_column(String(24), default="general")
    summary: Mapped[str] = mapped_column(String(400))
    session_id: Mapped[int | None] = mapped_column(Integer)
    pinned: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class HistoryNote(Base):
    """Always-in-the-loop private note grounded in the user's own words."""

    __tablename__ = "history_note"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # promised|agreed|declined|answered|asked|shared
    summary: Mapped[str] = mapped_column(String(400))
    quote: Mapped[str] = mapped_column(String(600))
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), index=True)
    session_id: Mapped[int | None] = mapped_column(Integer)
    pinned: Mapped[bool] = mapped_column(default=False)
    correction: Mapped[str | None] = mapped_column(String(400))
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class HistorySettings(Base):
    """Per-user toggle for always-in-the-loop note extraction."""

    __tablename__ = "history_settings"
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class Reminder(Base):
    """Fixed-text private reminder created via remind_me."""

    __tablename__ = "reminder"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(String(400))
    due_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    session_id: Mapped[int | None] = mapped_column(Integer)
    claimed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class OpenLoop(Base):
    """Tracked commitment / open loop extracted from chat or assigned explicitly."""

    __tablename__ = "open_loop"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(String(400))
    quote: Mapped[str] = mapped_column(String(600), default="")
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    session_id: Mapped[int | None] = mapped_column(Integer)
    last_nudged_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class BriefArtifact(Base):
    """Persisted morning brief / EOD digest for in-app delivery."""

    __tablename__ = "brief_artifact"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # morning_brief | end_of_day_digest
    user_id: Mapped[str | None] = mapped_column(String(128), index=True)  # None = workspace-wide
    period_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD local
    fingerprint: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
