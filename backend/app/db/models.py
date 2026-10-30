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
    company_code: Mapped[str] = mapped_column(String(32))
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


class Connection(Base):
    """An MCP server, an OpenAPI-described API, or the built-in function tools. Holds no secrets: auth
    config names environment variables, never their values."""

    __tablename__ = "connection"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(12))  # mcp | api | function
    config: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    health_status: Mapped[str] = mapped_column(String(12), default="unknown")  # unknown|healthy|unhealthy
    health_checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    health_detail: Mapped[str | None] = mapped_column(String(200))
    last_discovered_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class Capability(Base):
    """One normalized tool. `version` is the latest discovered definition; `published_version` is what
    production actually runs, so a changed upstream schema never goes live unreviewed."""

    __tablename__ = "capability"
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connection.id"), index=True)
    key: Mapped[str] = mapped_column(String(160), unique=True)  # stable id: <connection slug>.<tool name>
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String)
    input_schema: Mapped[dict] = mapped_column(JSON)
    output_schema: Mapped[dict | None] = mapped_column(JSON)
    implementation: Mapped[dict] = mapped_column(JSON)
    risk: Mapped[str] = mapped_column(String(24))  # effective: read | internal_write | external_message | destructive
    risk_override: Mapped[str | None] = mapped_column(String(24))  # an admin's reclassification; survives rediscovery
    permissions: Mapped[list] = mapped_column(JSON)  # roles allowed to invoke
    version: Mapped[int] = mapped_column(Integer, default=1)
    validated_version: Mapped[int | None] = mapped_column(Integer)
    published_version: Mapped[int | None] = mapped_column(Integer)
    removed: Mapped[bool] = mapped_column(default=False)  # no longer offered by its connection
    deprecated: Mapped[bool] = mapped_column(default=False)
    lifecycle: Mapped[str] = mapped_column(String(24), index=True)
    schema_hash: Mapped[str] = mapped_column(String(64))
    validation: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class CapabilityVersion(Base):
    __tablename__ = "capability_version"
    __table_args__ = (UniqueConstraint("capability_id", "version", name="uq_capability_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    capability_id: Mapped[int] = mapped_column(ForeignKey("capability.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String)
    input_schema: Mapped[dict] = mapped_column(JSON)
    output_schema: Mapped[dict | None] = mapped_column(JSON)
    implementation: Mapped[dict] = mapped_column(JSON)
    risk: Mapped[str] = mapped_column(String(24))
    schema_hash: Mapped[str] = mapped_column(String(64))
    validated: Mapped[bool] = mapped_column(default=False)  # a version can be (re)published only if validated
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


class KpiMapping(Base):
    """Which capability supplies a KPI's raw counts, reviewed by an admin before production use."""

    __tablename__ = "kpi_mapping"
    __table_args__ = (UniqueConstraint("kpi_key", "capability_id", name="uq_kpi_mapping"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kpi_key: Mapped[str] = mapped_column(String(64), index=True)
    capability_id: Mapped[int] = mapped_column(ForeignKey("capability.id"), index=True)
    field_map: Mapped[dict] = mapped_column(JSON)  # raw field -> path in the capability's output
    arg_template: Mapped[dict] = mapped_column(JSON)  # capability argument -> "{company_code}" etc.
    status: Mapped[str] = mapped_column(String(16), index=True)  # recommended|approved|rejected|superseded
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), server_default=func.now())


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
    """A skill (a reusable task) or an agent (a specialist configuration). Versioned and governed like a
    capability: draft -> validated -> published, with publication approved by a second admin."""

    __tablename__ = "asset"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_asset_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)  # skill | agent
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
