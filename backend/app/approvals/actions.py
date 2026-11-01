"""The only consequential operations the platform can perform on someone's behalf.

An action is declared here with its risk class, argument schema and executor. The executor is only ever
called by approvals.service after a human approval; nothing else (including the Copilot) imports it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import service as asset_service
from app.assets.definitions import MODELS as ASSET_MODELS
from app.core.security import Principal
from app.db.models import (
    ApprovalRequest,
    Asset,
    OutboundMessage,
    ReportSnapshot,
    ScorecardConfigVersion,
    WorkflowRun,
)
from app.kpi_registry.seed import KPIS
from app.reports.integrity import canonical_hash
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


# --- send_kpi_reminder ---------------------------------------------------------------------

class ReminderArgs(BaseModel):
    company_codes: list[str] = Field(min_length=1, max_length=200)
    period: str = Field(pattern=PERIOD_RE)
    kpi_key: str | None = None
    note: str = Field(default="", max_length=500)

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
    subject, body = _reminder_text(a)
    for code in a.company_codes:  # delivery channel is a later integration; queue for it
        db.add(OutboundMessage(approval_id=req.id, channel="email", company_code=code,
                               subject=subject, body=body))
    return {"queued": len(a.company_codes)}


# --- create_snapshot -----------------------------------------------------------------------

class SnapshotArgs(BaseModel):
    period: str = Field(pattern=PERIOD_RE)


def _create_snapshot(db: Session, req: ApprovalRequest, a: SnapshotArgs, approver: Principal) -> dict:
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
    run = db.get(WorkflowRun, a.run_id)
    if run is None or run.workflow != "monthly_review":
        raise ValueError("unknown report run")
    if run.status != "succeeded" or not run.result:
        raise ValueError("only a completed report can be published")
    if db.scalar(select(ReportSnapshot.id).where(ReportSnapshot.run_id == a.run_id)):
        raise ValueError("this report has already been published")


def _publish(db: Session, req: ApprovalRequest, a: PublishArgs, approver: Principal) -> dict:
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
    asset = db.get(Asset, a.asset_id)
    version = a.version or asset.version
    asset_service.publish_version(db, approver, asset, version)
    return {"kind": asset.kind, "key": asset.key, "published_version": version}


# --- activate_scorecard_config ---------------------------------------------------------------

class ActivateConfigArgs(BaseModel):
    version: int = Field(gt=1)


def _precheck_activate_config(db: Session, who: Principal, a: ActivateConfigArgs) -> dict:
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
