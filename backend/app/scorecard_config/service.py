from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.core.security import Principal
from app.db.models import ScorecardConfigVersion

from .rules import DEFAULT_RULES, ScorecardRules, effective_kpis


def active(db: Session) -> tuple[ScorecardRules, int]:
    row = db.scalar(select(ScorecardConfigVersion).where(ScorecardConfigVersion.status == "active"))
    return (ScorecardRules(**row.rules), row.version) if row else (DEFAULT_RULES, 1)


def next_version(db: Session) -> int:
    return max(db.scalar(select(func.max(ScorecardConfigVersion.version))) or 0, 1) + 1


def create_draft(db: Session, who: Principal, rules: ScorecardRules, note: str) -> ScorecardConfigVersion:
    row = ScorecardConfigVersion(version=next_version(db), status="draft", rules=rules.model_dump(),
                                 note=note[:300], created_by=who.user_id)
    db.add(row)
    audit(db, who, "scorecard_config_draft", f"v{row.version}")
    db.commit()
    return row


def diff(old: ScorecardRules, new: ScorecardRules) -> dict[str, dict]:
    """What changes, flattened so an approver can read it: 'score_cap', 'pillar_weights.retention',
    'kpi.kra_submission.target'. KPI changes are compared as effective values (a reset to the default counts)."""
    a, b = old.model_dump(), new.model_dump()
    out = {
        k: {"from": a[k], "to": b[k]}
        for k in a
        if a[k] != b[k] and k not in ("pillar_weights", "kpi_overrides", "added_kpis")
    }
    for p in a["pillar_weights"]:
        if a["pillar_weights"][p] != b["pillar_weights"][p]:
            out[f"pillar_weights.{p}"] = {"from": a["pillar_weights"][p], "to": b["pillar_weights"][p]}

    old_by = {k.key: k for k in effective_kpis(old.kpi_overrides, old.added_kpis)}
    new_by = {k.key: k for k in effective_kpis(new.kpi_overrides, new.added_kpis)}
    for key, kb in new_by.items():
        ka = old_by.get(key)
        if ka is None:
            out[f"kpi.{key}.added"] = {
                "from": None,
                "to": {
                    "label": next((x.label for x in new.added_kpis if x.key == key), key),
                    "pillar": kb.pillar,
                    "weight": kb.weight,
                    "target": kb.target,
                    "direction": kb.direction.value,
                },
            }
            continue
        for attr in ("weight", "target"):
            if getattr(ka, attr) != getattr(kb, attr):
                out[f"kpi.{key}.{attr}"] = {"from": getattr(ka, attr), "to": getattr(kb, attr)}
    for key in old_by:
        if key not in new_by:
            out[f"kpi.{key}.removed"] = {"from": key, "to": None}
    return out


def activate(db: Session, approver: Principal, version: int) -> None:
    """Called only by the approval executor."""
    for old in db.scalars(select(ScorecardConfigVersion).where(ScorecardConfigVersion.status == "active")):
        old.status = "superseded"
    row = db.scalar(select(ScorecardConfigVersion).where(ScorecardConfigVersion.version == version))
    row.status, row.activated_by, row.activated_at = "active", approver.user_id, datetime.now(UTC)
    audit(db, approver, "scorecard_config_activated", f"v{version}")
    db.flush()
    from app.knowledge.builtin import (
        seed_builtin,  # the built-in KPI document quotes weights and targets
    )

    seed_builtin(db, commit=False)  # inside the approval's own transaction: both change or neither does
