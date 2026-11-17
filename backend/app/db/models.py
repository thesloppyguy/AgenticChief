from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
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
    status: Mapped[str] = mapped_column(
        String(16), default="on_track"
    )  # on_track | at_risk | off_track
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
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_run.id", name="fk_report_snapshot_run_id")
    )
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
    status: Mapped[str] = mapped_column(
        String(16), index=True
    )  # queued|running|succeeded|failed|interrupted
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
    errors: Mapped[list | None] = mapped_column(
        JSON
    )  # exception type names only, never raw payloads
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
    context: Mapped[dict | None] = mapped_column(
        JSON
    )  # supporting context, e.g. the model's reason
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
    kind: Mapped[str] = mapped_column(
        String(32), index=True
    )  # status_red | ingestion_failed | watch_fired
    severity: Mapped[str] = mapped_column(String(12))  # low | medium | high | urgent
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("company.id"), index=True
    )  # None = group-wide
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
    params: Mapped[dict | None] = mapped_column(
        JSON
    )  # e.g. {"period": "previous", "sources": ["successfactors"]}
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_status: Mapped[str | None] = mapped_column(String(16))  # success | failed
    last_detail: Mapped[str | None] = mapped_column(String(200))
    claimed_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime()
    )  # set while a run is in flight
    created_by: Mapped[str] = mapped_column(String(128))


class Watch(Base):
    """A user-defined condition checked on a cadence. `condition` is validated by app.alerts.watches;
    the cadence lives on the paired JobSchedule, so watches reuse the scheduler's claiming and
    crash recovery rather than growing their own."""

    __tablename__ = "watch"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(128), index=True
    )  # the owner; alerts go only to them
    name: Mapped[str] = mapped_column(String(120))
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("company.id"), index=True
    )  # None = group
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


class DashboardLayout(Base):
    """Per-user Home layout: ordered built-in sections, pinned chat widgets, pulse KPIs."""

    __tablename__ = "dashboard_layout"
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    widgets: Mapped[list] = mapped_column(JSON, default=list)
    pulse_cells: Mapped[list] = mapped_column(JSON, default=list)
    pulse_hidden: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


# --- SF-shaped workforce census (demo simulation; not the Person governance roster) -----------


class Employee(Base):
    """Current Employee Central-style snapshot for one simulated worker."""

    __tablename__ = "employee"
    __table_args__ = (Index("ix_employee_company_status", "company_code", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ps_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    company_code: Mapped[str] = mapped_column(String(32), index=True)
    legal_entity: Mapped[str] = mapped_column(String(120), default="")
    business_unit: Mapped[str] = mapped_column(String(120), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    job_code: Mapped[str] = mapped_column(String(48), default="")
    job_title: Mapped[str] = mapped_column(String(120), default="")
    job_function: Mapped[str] = mapped_column(String(120), default="")
    grade_cadre: Mapped[str] = mapped_column(String(32), default="")
    band: Mapped[str] = mapped_column(String(32), default="")
    employment_type: Mapped[str] = mapped_column(String(48), default="Permanent")
    appointment_type: Mapped[str] = mapped_column(String(48), default="")
    employee_group: Mapped[str] = mapped_column(String(48), default="")
    manager_ps_number: Mapped[str | None] = mapped_column(String(32), index=True)
    position_id: Mapped[str] = mapped_column(String(48), default="")
    hire_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    joining_date: Mapped[str] = mapped_column(String(10))
    separation_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | separated
    time_in_company_months: Mapped[int] = mapped_column(Integer, default=0)
    time_in_position_months: Mapped[int] = mapped_column(Integer, default=0)
    is_trainee: Mapped[bool] = mapped_column(default=False)
    contract_training_end_date: Mapped[str | None] = mapped_column(String(10))
    top_talent: Mapped[bool] = mapped_column(default=False)
    cpr_band: Mapped[int] = mapped_column(Integer, default=0)  # CPR scale; 7+ = top talent band
    willing_to_relocate: Mapped[bool] = mapped_column(default=False)
    base_location: Mapped[str] = mapped_column(String(120), default="")
    full_name: Mapped[str] = mapped_column(String(120), default="")
    archetype: Mapped[str] = mapped_column(String(16), default="steady")


class EmployeePerformance(Base):
    """Annual performance / feedback signals for one employee."""

    __tablename__ = "employee_performance"
    __table_args__ = (
        UniqueConstraint("employee_id", "assessment_year", name="uq_emp_perf_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    assessment_year: Mapped[int] = mapped_column(Integer)
    mvg_rating: Mapped[float | None] = mapped_column(Float)
    cp_rating: Mapped[float | None] = mapped_column(Float)
    pdr_rating: Mapped[float | None] = mapped_column(Float)
    feedback_entries_ytd: Mapped[int] = mapped_column(Integer, default=0)
    kra_submitted: Mapped[bool] = mapped_column(default=False)
    mid_term_completed: Mapped[bool] = mapped_column(default=False)


class EmployeeLearning(Base):
    """Learning / TNI / course completion events."""

    __tablename__ = "employee_learning"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    course_name: Mapped[str] = mapped_column(String(200))
    completed_on: Mapped[str | None] = mapped_column(String(10))
    l1_rating_5: Mapped[float | None] = mapped_column(Float)
    tni_identified: Mapped[bool] = mapped_column(default=False)
    tni_fulfilled: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(32), default="course")  # course | leadership_program


class EmployeeSkill(Base):
    """Role skills, certifications, and language proficiency."""

    __tablename__ = "employee_skill"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    skill_type: Mapped[str] = mapped_column(String(24))  # role_skill | certification | language
    name: Mapped[str] = mapped_column(String(120))
    proficiency: Mapped[str] = mapped_column(String(48), default="")
    mapped_to_role: Mapped[bool] = mapped_column(default=False)
    valid_until: Mapped[str | None] = mapped_column(String(10))


class EmployeeDevelopment(Base):
    """Development centre / PLI / IDP / nine-box talent signals."""

    __tablename__ = "employee_development"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", name="uq_emp_dev_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    dc_type: Mapped[str | None] = mapped_column(String(48))
    dc_score: Mapped[float | None] = mapped_column(Float)
    pli_completed: Mapped[bool] = mapped_column(default=False)
    has_idp: Mapped[bool] = mapped_column(default=False)
    nine_box: Mapped[str | None] = mapped_column(String(24))


class EmployeeEvent(Base):
    """Mobility and exit timeline (hire / promote / transfer / deputation / resign / separate)."""

    __tablename__ = "employee_event"
    __table_args__ = (Index("ix_employee_event_emp_date", "employee_id", "effective_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(24))
    effective_date: Mapped[str] = mapped_column(String(10))
    reason_code: Mapped[str] = mapped_column(String(64), default="")
    from_ic: Mapped[str | None] = mapped_column(String(32))
    to_ic: Mapped[str | None] = mapped_column(String(32))
    from_grade: Mapped[str | None] = mapped_column(String(32))
    to_grade: Mapped[str | None] = mapped_column(String(32))
    regrettable: Mapped[bool] = mapped_column(default=False)
