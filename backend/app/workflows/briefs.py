"""Morning brief and end-of-day digest builders (in-app delivery)."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.engine import _raise
from app.core.config import settings
from app.core.security import Principal, Role
from app.db.models import Alert, ApprovalRequest, BriefArtifact, OpenLoop
from app.services.scorecard import current_period

SYSTEM = Principal("scheduler", Role.VIEWER, None)


def _local_today() -> str:
    try:
        tz = ZoneInfo(settings.user_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date().isoformat()


def _fingerprint(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _context(db: Session) -> dict[str, Any]:
    period = current_period()
    reds: list[str] = []
    try:
        from app.services.scorecard import build_scorecard

        card = build_scorecard(db, SYSTEM, period)
        if card["group"]["status"] == "red":
            reds.append(f"Group score {card['group']['score']:.1f} is red")
        for c in card.get("companies") or []:
            if c.get("status") == "red":
                reds.append(f"{c['code']} is red ({c.get('score')})")
    except Exception:
        pass

    alerts = list(
        db.scalars(
            select(Alert).order_by(Alert.id.desc()).limit(8)
        )
    )
    pending = list(
        db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.id.desc())
            .limit(8)
        )
    )
    loops = list(
        db.scalars(
            select(OpenLoop)
            .where(OpenLoop.status == "open")
            .order_by(OpenLoop.id.desc())
            .limit(10)
        )
    )
    return {
        "period": period,
        "reds": reds[:10],
        "alerts": [{"title": a.title, "severity": a.severity, "kind": a.kind} for a in alerts],
        "approvals": [
            {"id": a.id, "action": a.action, "summary": (a.summary or "")[:120]}
            for a in pending
        ],
        "open_loops": [
            {
                "id": L.id,
                "description": L.description,
                "due_at": L.due_at.isoformat() if L.due_at else None,
                "user_id": L.user_id,
            }
            for L in loops
        ],
    }


def _render_morning(ctx: dict[str, Any], due_notes: list[str]) -> str:
    lines = [
        f"# Morning brief — {ctx['period']}",
        "",
        "## Scorecard attention",
    ]
    lines += [f"- {r}" for r in ctx["reds"]] or ["- Nothing red right now."]
    lines += ["", "## Open approvals"]
    lines += [f"- #{a['id']} {a['action']}: {a['summary']}" for a in ctx["approvals"]] or [
        "- None pending."
    ]
    lines += ["", "## Recent alerts"]
    lines += [f"- [{a['severity']}] {a['title']}" for a in ctx["alerts"][:5]] or ["- Quiet."]
    lines += ["", "## Open loops"]
    lines += [
        f"- {L['description']}" + (f" (due {L['due_at'][:10]})" if L.get("due_at") else "")
        for L in ctx["open_loops"][:5]
    ] or ["- None."]
    if due_notes:
        lines += ["", "## Notes due soon", *[f"- {n}" for n in due_notes]]
    return "\n".join(lines)


def _render_eod(ctx: dict[str, Any], noted_today: list[str]) -> str:
    lines = [
        f"# End of day — {ctx['period']}",
        "",
        "## Still red",
    ]
    lines += [f"- {r}" for r in ctx["reds"]] or ["- Clear."]
    lines += ["", "## Approvals waiting"]
    lines += [f"- #{a['id']} {a['action']}" for a in ctx["approvals"]] or ["- None."]
    lines += ["", "## Open loops"]
    lines += [f"- {L['description']}" for L in ctx["open_loops"][:8]] or ["- None."]
    if noted_today:
        lines += ["", "## Noted today", *[f"- {n}" for n in noted_today]]
    return "\n".join(lines)


def _persist_and_alert(
    db: Session,
    *,
    kind: str,
    title: str,
    body: str,
    fingerprint: str,
    user_id: str | None = None,
) -> BriefArtifact | None:
    today = _local_today()
    existing = db.scalar(
        select(BriefArtifact).where(
            BriefArtifact.kind == kind,
            BriefArtifact.period_date == today,
            BriefArtifact.user_id == user_id,
        ).order_by(BriefArtifact.id.desc())
    )
    if existing and existing.fingerprint == fingerprint:
        return None  # unchanged — suppress
    art = BriefArtifact(
        kind=kind,
        user_id=user_id,
        period_date=today,
        fingerprint=fingerprint,
        title=title,
        body=body,
    )
    db.add(art)
    db.flush()
    period = current_period()
    _raise(
        db,
        kind=kind,
        severity="low",
        company_id=None,
        entity=kind,
        period=period,
        title=title,
        detail={"brief_id": art.id, "period_date": today},
        dedupe_key=f"{kind}:{today}:{fingerprint}",
        audience_user_id=user_id,
    )
    db.commit()
    db.refresh(art)
    return art


def run_morning_brief(db: Session) -> str:
    ctx = _context(db)
    # Workspace-level brief (no per-user history notes in the shared artifact)
    body = _render_morning(ctx, [])
    fp = _fingerprint({"kind": "morning", **ctx})
    art = _persist_and_alert(
        db,
        kind="morning_brief",
        title=f"Morning brief {_local_today()}",
        body=body,
        fingerprint=fp,
    )
    return "suppressed (unchanged)" if art is None else f"brief #{art.id}"


def run_eod_digest(db: Session) -> str:
    ctx = _context(db)
    body = _render_eod(ctx, [])
    fp = _fingerprint({"kind": "eod", **ctx})
    art = _persist_and_alert(
        db,
        kind="end_of_day_digest",
        title=f"End of day {_local_today()}",
        body=body,
        fingerprint=fp,
    )
    return "suppressed (unchanged)" if art is None else f"digest #{art.id}"


def latest_brief(db: Session, kind: str | None = None) -> BriefArtifact | None:
    q = select(BriefArtifact).order_by(BriefArtifact.id.desc()).limit(1)
    if kind:
        q = (
            select(BriefArtifact)
            .where(BriefArtifact.kind == kind)
            .order_by(BriefArtifact.id.desc())
            .limit(1)
        )
    return db.scalar(q)
