"""Wipe scorecard org + related demo state so L&T fixtures can load cleanly."""
from __future__ import annotations

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    AlertRead,
    ApprovalEvent,
    ApprovalRequest,
    BriefArtifact,
    Company,
    Department,
    Goal,
    HistoryNote,
    KpiRecord,
    ManualInputHistory,
    MockCompanyData,
    OpenLoop,
    OutboundMessage,
    Person,
    Reminder,
    ReportSnapshot,
    UserMemory,
    Watch,
    WorkflowEvent,
    WorkflowRun,
)


def reset_org(db: Session) -> dict[str, int]:
    """Delete companies and dependent demo rows. Safe for local SQLite reseed."""
    counts: dict[str, int] = {}

    def _del(model, label: str) -> None:
        n = db.execute(delete(model)).rowcount or 0
        counts[label] = n

    # Children first where FKs exist without ON DELETE CASCADE.
    for model, label in (
        (AlertRead, "alert_reads"),
        (Alert, "alerts"),
        (Watch, "watches"),
        (OutboundMessage, "outbound"),
        (ApprovalEvent, "approval_events"),
        (ApprovalRequest, "approvals"),
        (WorkflowEvent, "workflow_events"),
        (KpiRecord, "kpi_records"),
        (ManualInputHistory, "manual_inputs"),
        (MockCompanyData, "mock_company_data"),
        (Goal, "goals"),
        (Department, "departments"),
        (Person, "people"),
        (UserMemory, "memories"),
        (HistoryNote, "history_notes"),
        (OpenLoop, "open_loops"),
        (Reminder, "reminders"),
        (BriefArtifact, "briefs"),
    ):
        _del(model, label)

    # Snapshots are immutable via ORM events — bypass with raw SQL.
    try:
        n = db.execute(text("DELETE FROM report_snapshot")).rowcount or 0
        counts["snapshots"] = n
    except Exception:
        counts["snapshots"] = 0

    try:
        n = db.execute(delete(WorkflowRun)).rowcount or 0
        counts["workflow_runs"] = n
    except Exception:
        counts["workflow_runs"] = 0

    _del(Company, "companies")
    db.commit()
    return counts
