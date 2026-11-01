"""Thin People / Departments / Goals CRUD for the L&T Group CHRO org model."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal, require_editor
from app.db.models import Department, Goal, Person
from app.db.session import get_db

router = APIRouter(tags=["org"])


def _person_out(p: Person) -> dict:
    return {
        "id": p.id,
        "full_name": p.full_name,
        "role": p.role,
        "email": p.email,
        "company_code": p.company_code,
        "is_principal": p.is_principal,
        "authority_scope": p.authority_scope or [],
        "department_slugs": p.department_slugs or [],
        "preferred_channel": p.preferred_channel,
        "response_sla_hours": p.response_sla_hours,
    }


def _dept_out(d: Department) -> dict:
    return {
        "id": d.id,
        "slug": d.slug,
        "title": d.title,
        "company_code": d.company_code,
        "specialist_key": d.specialist_key,
        "head_person_id": d.head_person_id,
        "authority_level": d.authority_level,
        "charter": d.charter,
        "headcount": d.headcount,
    }


def _goal_out(g: Goal) -> dict:
    return {
        "id": g.id,
        "department_id": g.department_id,
        "period_type": g.period_type,
        "period_value": g.period_value,
        "key_result": g.key_result,
        "target": g.target,
        "current": g.current,
        "status": g.status,
        "pillar_key": g.pillar_key,
    }


@router.get("/people")
def list_people(
    company_code: str | None = None,
    db: Session = Depends(get_db),
    _: Principal = Depends(get_principal),
):
    q = select(Person).order_by(Person.id)
    if company_code is not None:
        code = company_code.strip().upper() or None
        q = q.where(Person.company_code == code)
    return [_person_out(p) for p in db.scalars(q)]


class PersonIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    email: str = ""
    company_code: str | None = None
    is_principal: bool = False
    authority_scope: list[str] = Field(default_factory=list)
    department_slugs: list[str] = Field(default_factory=list)
    preferred_channel: str = "any"
    response_sla_hours: int | None = None


@router.post("/people", status_code=201)
def create_person(body: PersonIn, db: Session = Depends(get_db), _: Principal = Depends(require_editor)):
    code = body.company_code.strip().upper() if body.company_code else None
    p = Person(
        full_name=body.full_name.strip(),
        role=body.role.strip(),
        email=body.email.strip(),
        company_code=code,
        is_principal=body.is_principal,
        authority_scope=body.authority_scope,
        department_slugs=body.department_slugs,
        preferred_channel=body.preferred_channel,
        response_sla_hours=body.response_sla_hours,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _person_out(p)


@router.get("/departments")
def list_departments(
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Principal = Depends(get_principal),
):
    q = select(Department).order_by(Department.id)
    if company_code is not None:
        code = company_code.strip().upper() or None
        q = q.where(Department.company_code == code)
    return [_dept_out(d) for d in db.scalars(q)]


class DepartmentIn(BaseModel):
    slug: str = Field(min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=120)
    company_code: str | None = None
    specialist_key: str | None = None
    head_person_id: int | None = None
    authority_level: str = "propose_only"
    charter: dict | None = None
    headcount: int | None = None


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, db: Session = Depends(get_db), _: Principal = Depends(require_editor)):
    code = body.company_code.strip().upper() if body.company_code else None
    d = Department(
        slug=body.slug.strip().lower(),
        title=body.title.strip(),
        company_code=code,
        specialist_key=body.specialist_key,
        head_person_id=body.head_person_id,
        authority_level=body.authority_level,
        charter=body.charter,
        headcount=body.headcount,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _dept_out(d)


@router.get("/goals")
def list_goals(
    company_code: str | None = None,
    department_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: Principal = Depends(get_principal),
):
    q = select(Goal).order_by(Goal.id)
    if department_id is not None:
        q = q.where(Goal.department_id == department_id)
    elif company_code is not None:
        code = company_code.strip().upper() or None
        dept_ids = list(db.scalars(select(Department.id).where(Department.company_code == code)))
        q = q.where(Goal.department_id.in_(dept_ids or [-1]))
    if status:
        q = q.where(Goal.status == status)
    return [_goal_out(g) for g in db.scalars(q)]


class GoalIn(BaseModel):
    department_id: int
    period_type: str = "quarter"
    period_value: str = ""
    key_result: str = Field(min_length=1, max_length=400)
    target: str = ""
    current: str = ""
    status: str = "on_track"
    pillar_key: str | None = None


@router.post("/goals", status_code=201)
def create_goal(body: GoalIn, db: Session = Depends(get_db), _: Principal = Depends(require_editor)):
    if not db.get(Department, body.department_id):
        raise HTTPException(404, "department not found")
    g = Goal(
        department_id=body.department_id,
        period_type=body.period_type,
        period_value=body.period_value,
        key_result=body.key_result.strip(),
        target=body.target,
        current=body.current,
        status=body.status,
        pillar_key=body.pillar_key,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _goal_out(g)
