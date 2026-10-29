"""Function tools: Python callables registered in code (never loaded from user input)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, Role
from app.db.models import Company

from ..types import DiscoveredTool, InvocationError

_SYSTEM = Principal("system", Role.ADMIN, None)


@dataclass(frozen=True)
class FunctionDef:
    name: str
    description: str
    args_model: type[BaseModel]
    output_schema: dict | None
    fn: Callable[[Session, BaseModel], dict]
    risk: str = "read"


class _NoArgs(BaseModel):
    pass


class _PeriodArgs(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Fiscal period, YYYY-MM")


def _list_companies(db: Session, _: BaseModel) -> dict:
    rows = db.execute(select(Company.code, Company.name).where(Company.active).order_by(Company.code)).all()
    return {"companies": [{"code": c, "name": n} for c, n in rows]}


def _group_score(db: Session, a: _PeriodArgs) -> dict:  # type: ignore[override]
    from app.services.scorecard import (
        build_scorecard,  # lazy: scorecard -> ingestion registry -> here
    )

    card = build_scorecard(db, _SYSTEM, a.period)
    g = card["group"]
    return {"score": g["score"], "status": g["status"], "pillar_coverage": g["pillar_coverage"],
            "companies_with_data": g["companies_with_data"], "companies_in_scope": g["companies_in_scope"]}


FUNCTIONS: dict[str, FunctionDef] = {f.name: f for f in (
    FunctionDef("list_companies", "List the active companies in the group.", _NoArgs,
                {"type": "object", "properties": {"companies": {"type": "array"}}, "required": ["companies"]},
                _list_companies),
    FunctionDef("group_score", "The Group HR score for a period, from the scoring service.", _PeriodArgs,
                {"type": "object", "properties": {"score": {"type": ["number", "null"]},
                                                  "status": {"type": ["string", "null"]},
                                                  "pillar_coverage": {"type": "number"},
                                                  "companies_with_data": {"type": "integer"},
                                                  "companies_in_scope": {"type": "integer"}},
                 "required": ["score", "pillar_coverage"]},
                _group_score),
)}


def discover() -> list[DiscoveredTool]:
    return [DiscoveredTool(name=f.name, description=f.description, input_schema=f.args_model.model_json_schema(),
                           output_schema=f.output_schema, implementation={"type": "function", "ref": f.name},
                           risk=f.risk) for f in FUNCTIONS.values()]


def call(db: Session, ref: str, args: dict) -> dict:
    f = FUNCTIONS.get(ref)
    if f is None:
        raise InvocationError("unknown function")
    return f.fn(db, f.args_model(**args))
