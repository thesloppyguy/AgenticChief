"""Personal Home dashboard layout: built-in sections + pinned chat widgets + pulse KPIs."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Principal, Role
from app.db.models import ApprovalRequest, DashboardLayout

SECTION_KEYS = (
    "brief",
    "pulse",
    "scorecard",
    "exception",
    "issues",
    "pinned_widgets",
)
MAX_WIDGETS = 12
MAX_PULSE_CELLS = 8
MAX_ARTIFACT_BYTES = 48_000

# Live metric sources resolved when Home / pulse is served (not frozen snapshots).
PULSE_SOURCES = (
    "pending_approvals",
    "draft_chro_actions",
)
PULSE_SOURCE_META: dict[str, dict[str, str]] = {
    "pending_approvals": {
        "default_label": "Pending actions",
        "default_note": "awaiting approval",
        "default_tone": "alert",
    },
    "draft_chro_actions": {
        "default_label": "Draft CHRO actions",
        "default_note": "ready for review",
        "default_tone": "alert",
    },
}


class SectionSpec(BaseModel):
    key: str
    visible: bool = True

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip()
        if v not in SECTION_KEYS:
            raise ValueError(f"unknown section key: {v}")
        return v


class WidgetSpec(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=200)
    kind: str = Field(min_length=1, max_length=64)
    artifact: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("widget id required")
        return v[:64]

    @field_validator("artifact")
    @classmethod
    def _artifact(cls, v: dict[str, Any]) -> dict[str, Any]:
        # Keep payloads bounded; Home stores a snapshot of the chat card.
        import json

        raw = json.dumps(v, default=str)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError("widget artifact is too large")
        return v


class PulseCellSpec(BaseModel):
    """Personal Workforce Pulse KPI tile (live source, not a scored scorecard KPI)."""

    id: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    source: str = Field(min_length=1, max_length=64)
    unit: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=200)
    tone: str = Field(default="", max_length=32)
    visible: bool = True

    @field_validator("id", "key")
    @classmethod
    def _id_key(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("required")
        return v[:64]

    @field_validator("source")
    @classmethod
    def _source(cls, v: str) -> str:
        v = v.strip()
        if v not in PULSE_SOURCES:
            raise ValueError(
                f"unknown pulse source '{v}' (allowed: {', '.join(PULSE_SOURCES)})"
            )
        return v


class LayoutPayload(BaseModel):
    sections: list[SectionSpec]
    widgets: list[WidgetSpec] = Field(default_factory=list)
    pulse_cells: list[PulseCellSpec] = Field(default_factory=list)
    pulse_hidden: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize(self) -> LayoutPayload:
        if len(self.widgets) > MAX_WIDGETS:
            raise ValueError(f"at most {MAX_WIDGETS} pinned widgets")
        if len(self.pulse_cells) > MAX_PULSE_CELLS:
            raise ValueError(f"at most {MAX_PULSE_CELLS} personal pulse KPIs")
        seen_ids: set[str] = set()
        for w in self.widgets:
            if w.id in seen_ids:
                raise ValueError(f"duplicate widget id: {w.id}")
            seen_ids.add(w.id)

        seen_pulse: set[str] = set()
        for c in self.pulse_cells:
            if c.id in seen_pulse:
                raise ValueError(f"duplicate pulse cell id: {c.id}")
            seen_pulse.add(c.id)

        # Deduplicate hide list; keep stable order.
        hidden: list[str] = []
        seen_h: set[str] = set()
        for k in self.pulse_hidden:
            key = str(k or "").strip()
            if not key or key in seen_h:
                continue
            seen_h.add(key)
            hidden.append(key[:64])
        self.pulse_hidden = hidden

        by_key = {s.key: s for s in self.sections}
        # Fill missing with defaults so callers can send a partial reorder.
        for k in SECTION_KEYS:
            if k not in by_key:
                by_key[k] = SectionSpec(key=k, visible=True)
        # Preserve caller order for known keys, then append any filled defaults.
        ordered: list[SectionSpec] = []
        seen: set[str] = set()
        for s in self.sections:
            if s.key not in seen:
                ordered.append(by_key[s.key])
                seen.add(s.key)
        for k in SECTION_KEYS:
            if k not in seen:
                ordered.append(by_key[k])
                seen.add(k)
        self.sections = ordered
        return self


def default_layout() -> dict:
    return {
        "sections": [{"key": k, "visible": True} for k in SECTION_KEYS],
        "widgets": [],
        "pulse_cells": [],
        "pulse_hidden": [],
    }


def _row_to_dict(row: DashboardLayout | None) -> dict:
    if row is None:
        return default_layout()
    try:
        payload = LayoutPayload(
            sections=row.sections or [],
            widgets=row.widgets or [],
            pulse_cells=getattr(row, "pulse_cells", None) or [],
            pulse_hidden=getattr(row, "pulse_hidden", None) or [],
        )
        return payload.model_dump()
    except ValueError:
        return default_layout()


def get_layout(db: Session, user_id: str) -> dict:
    row = db.get(DashboardLayout, user_id)
    out = _row_to_dict(row)
    out["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
    out["pulse_sources"] = [
        {"key": k, **PULSE_SOURCE_META[k]} for k in PULSE_SOURCES
    ]
    return out


def parse_layout(data: dict | LayoutPayload) -> LayoutPayload:
    if isinstance(data, LayoutPayload):
        return data
    return LayoutPayload.model_validate(data)


def apply_layout(db: Session, user_id: str, data: dict | LayoutPayload) -> dict:
    payload = parse_layout(data)
    dumped = payload.model_dump()
    row = db.get(DashboardLayout, user_id)
    now = datetime.now(UTC)
    if row is None:
        row = DashboardLayout(
            user_id=user_id,
            sections=dumped["sections"],
            widgets=dumped["widgets"],
            pulse_cells=dumped["pulse_cells"],
            pulse_hidden=dumped["pulse_hidden"],
            updated_at=now,
        )
        db.add(row)
    else:
        row.sections = dumped["sections"]
        row.widgets = dumped["widgets"]
        row.pulse_cells = dumped["pulse_cells"]
        row.pulse_hidden = dumped["pulse_hidden"]
        row.updated_at = now
    db.flush()
    return get_layout(db, user_id)


def diff_layout(before: dict, after: LayoutPayload) -> list[str]:
    """Human-readable change lines for Approvals precheck."""
    changes: list[str] = []
    before_sections = {s["key"]: s for s in before.get("sections") or []}
    after_order = [s.key for s in after.sections]
    before_order = [s["key"] for s in before.get("sections") or [] if s.get("key") in SECTION_KEYS]
    # Normalize before order to include all keys
    for k in SECTION_KEYS:
        if k not in before_order:
            before_order.append(k)

    for s in after.sections:
        prev = before_sections.get(s.key) or {"key": s.key, "visible": True}
        was = bool(prev.get("visible", True))
        if was != s.visible:
            changes.append(f"{'Show' if s.visible else 'Hide'} {s.key.replace('_', ' ')}")

    if after_order != before_order:
        changes.append("Reorder sections: " + " → ".join(after_order))

    before_widgets = {w.get("id"): w for w in (before.get("widgets") or []) if w.get("id")}
    after_widgets = {w.id: w for w in after.widgets}
    for wid, w in after_widgets.items():
        if wid not in before_widgets:
            title = (w.title or w.kind or wid).strip()
            changes.append(f"Pin widget “{title}”")
        elif before_widgets[wid].get("kind") != w.kind or before_widgets[wid].get("title") != w.title:
            changes.append(f"Update widget “{(w.title or wid).strip()}”")
    for wid, w in before_widgets.items():
        if wid not in after_widgets:
            title = (w.get("title") or w.get("kind") or wid).strip()
            changes.append(f"Remove widget “{title}”")

    before_ids = [w.get("id") for w in (before.get("widgets") or []) if w.get("id")]
    after_ids = [w.id for w in after.widgets]
    if set(before_ids) == set(after_ids) and before_ids != after_ids and after_ids:
        changes.append("Reorder pinned widgets")

    before_pulse = {c.get("id"): c for c in (before.get("pulse_cells") or []) if c.get("id")}
    after_pulse = {c.id: c for c in after.pulse_cells}
    for cid, c in after_pulse.items():
        label = (c.label or c.key or cid).strip()
        if cid not in before_pulse:
            changes.append(f"Add pulse KPI “{label}”")
        else:
            prev = before_pulse[cid]
            if (
                prev.get("source") != c.source
                or prev.get("label") != c.label
                or bool(prev.get("visible", True)) != c.visible
            ):
                changes.append(f"Update pulse KPI “{label}”")
    for cid, c in before_pulse.items():
        if cid not in after_pulse:
            label = (c.get("label") or c.get("key") or cid).strip()
            changes.append(f"Remove pulse KPI “{label}”")

    before_hidden = [str(k) for k in (before.get("pulse_hidden") or [])]
    after_hidden = list(after.pulse_hidden)
    for k in after_hidden:
        if k not in before_hidden:
            changes.append(f"Hide built-in pulse “{k.replace('_', ' ')}”")
    for k in before_hidden:
        if k not in after_hidden:
            changes.append(f"Show built-in pulse “{k.replace('_', ' ')}”")

    return changes


def _visible_pending_approvals(db: Session, who: Principal) -> int:
    """Pending approvals this principal can see (admins: inbox; others: own requests)."""
    q = select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "pending")
    if who.role is not Role.ADMIN:
        q = q.where(ApprovalRequest.requested_by == who.user_id)
    return int(db.scalar(q) or 0)


def resolve_pulse_source(db: Session, who: Principal, source: str) -> float | int | None:
    if source == "pending_approvals":
        return _visible_pending_approvals(db, who)
    if source == "draft_chro_actions":
        from app.workforce import loader as wf_loader

        drafts = (wf_loader.draft_actions() or {}).get("drafts") or []
        return len(drafts)
    return None


def resolve_personal_pulse_cells(db: Session, who: Principal) -> list[dict[str, Any]]:
    """Live pulse tiles from the user's layout (visible only)."""
    layout = get_layout(db, who.user_id)
    out: list[dict[str, Any]] = []
    for raw in layout.get("pulse_cells") or []:
        if not isinstance(raw, dict) or raw.get("visible") is False:
            continue
        source = str(raw.get("source") or "")
        meta = PULSE_SOURCE_META.get(source) or {}
        value = resolve_pulse_source(db, who, source)
        if value is None:
            continue
        out.append(
            {
                "key": raw.get("key") or source,
                "label": (raw.get("label") or meta.get("default_label") or source),
                "value": value,
                "unit": raw.get("unit") or "",
                "note": raw.get("note") or meta.get("default_note") or "",
                "tone": raw.get("tone") or meta.get("default_tone") or "",
                "personal": True,
                "source": source,
            }
        )
    return out


def merge_pulse_cells(
    fixture_cells: list[dict[str, Any]] | None,
    db: Session,
    who: Principal,
) -> list[dict[str, Any]]:
    """Built-in fixture cells (minus pulse_hidden) + personal extras."""
    layout = get_layout(db, who.user_id)
    hidden = set(layout.get("pulse_hidden") or [])
    base = [
        c
        for c in (fixture_cells or [])
        if isinstance(c, dict) and c.get("key") not in hidden
    ]
    return base + resolve_personal_pulse_cells(db, who)
