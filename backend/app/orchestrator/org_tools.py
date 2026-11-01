"""Copilot tools for People / Goals (L&T Group CHRO org model)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.db.models import Department, Goal, Person

ORG_TOOLS: list[dict[str, Any]] = sorted(
    [
        {
            "name": "list_people",
            "description": "List roster people for the Group (omit company_code) or one IC. "
            "Use for CHRO questions about who owns hiring, retention, or People goals.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "company_code": {
                        "type": "string",
                        "description": "IC code e.g. LTTS, or empty/omit for Group-level people.",
                    }
                },
            },
        },
        {
            "name": "list_goals",
            "description": "List People / department goals (OKRs), optionally filtered by company or status "
            "(on_track | at_risk | off_track). Goals may link to scorecard pillars via pillar_key.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "company_code": {"type": "string"},
                    "status": {"type": "string", "enum": ["on_track", "at_risk", "off_track"]},
                },
            },
        },
    ],
    key=lambda t: t["name"],
)


def dispatch(name: str, args: dict, db: Session, who: Principal) -> dict:
    if name == "list_people":
        code = (args.get("company_code") or "").strip().upper() or None
        q = select(Person).order_by(Person.id)
        if "company_code" in args:
            q = q.where(Person.company_code == code)
        rows = list(db.scalars(q).limit(50))
        return {
            "people": [
                {
                    "id": p.id,
                    "full_name": p.full_name,
                    "role": p.role,
                    "email": p.email,
                    "company_code": p.company_code,
                    "is_principal": p.is_principal,
                    "department_slugs": p.department_slugs or [],
                    "preferred_channel": p.preferred_channel,
                    "authority_scope": p.authority_scope or [],
                }
                for p in rows
            ]
        }
    if name == "list_goals":
        code = (args.get("company_code") or "").strip().upper() or None
        status = args.get("status")
        q = select(Goal, Department).join(Department, Goal.department_id == Department.id)
        if code is not None or "company_code" in args:
            q = q.where(Department.company_code == code)
        if status:
            q = q.where(Goal.status == status)
        out = []
        for g, d in db.execute(q.limit(80)):
            out.append(
                {
                    "key_result": g.key_result,
                    "target": g.target,
                    "current": g.current,
                    "status": g.status,
                    "pillar_key": g.pillar_key,
                    "period": f"{g.period_type}:{g.period_value}",
                    "department": d.title,
                    "company_code": d.company_code,
                }
            )
        return {"goals": out}
    return {"error": f"unknown org tool {name}"}
