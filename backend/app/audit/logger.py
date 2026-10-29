from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.security import Principal
from app.db.models import AuditEvent

_PII = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\+?\d[\d\s-]{8,}\d"),
]


def redact(text: str) -> str:
    for p in _PII:
        text = p.sub("[redacted]", text)
    return text


def audit(db: Session, who: Principal, action: str, target: str | None = None, detail=None) -> None:
    """Append-only; an audit failure must never break the request."""
    try:
        db.add(AuditEvent(actor=who.user_id, role=who.role.value, action=action,
                          target=target, detail=detail))
        db.flush()
    except Exception:  # noqa: BLE001
        pass
