from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.capabilities import recommend as recommender
from app.capabilities import service
from app.capabilities.invoke import invoke
from app.capabilities.types import CapabilityError, ConfigError, DiscoveryError
from app.core.security import Principal, require_admin
from app.db.models import Capability, CapabilityVersion, Connection, KpiMapping
from app.db.session import get_db

router = APIRouter()
MAX_TEST_OUTPUT_CHARS = 20_000


def admin(who: Principal = Depends(require_admin)) -> Principal:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    return who


def _http(e: CapabilityError) -> HTTPException:
    return HTTPException(502 if isinstance(e, DiscoveryError) else 422, str(e))


def _conn(db: Session, conn_id: int) -> Connection:
    c = db.get(Connection, conn_id)
    if c is None:
        raise HTTPException(404, "Connection not found")
    return c


def _cap(db: Session, cap_id: int) -> Capability:
    c = db.get(Capability, cap_id)
    if c is None:
        raise HTTPException(404, "Capability not found")
    return c


def _conn_out(db: Session, c: Connection) -> dict:
    n = db.scalar(select(func.count(Capability.id)).where(Capability.connection_id == c.id)) or 0
    return {"id": c.id, "slug": c.slug, "name": c.name, "type": c.type, "config": service.public_config(c),
            "active": c.active, "health_status": c.health_status, "health_checked_at": c.health_checked_at,
            "health_detail": c.health_detail, "last_discovered_at": c.last_discovered_at,
            "capability_count": n, "created_by": c.created_by}


def _cap_out(c: Capability) -> dict:
    return {"id": c.id, "connection_id": c.connection_id, "key": c.key, "name": c.name,
            "description": c.description, "risk": c.risk, "risk_overridden": c.risk_override is not None,
            "version": c.version, "validated_version": c.validated_version, "published_version": c.published_version,
            "lifecycle": c.lifecycle, "permissions": c.permissions, "implementation": c.implementation,
            "validation": c.validation}


def _mapping_out(m: KpiMapping, cap: Capability | None = None) -> dict:
    return {"id": m.id, "kpi_key": m.kpi_key, "capability_id": m.capability_id,
            "capability_key": cap.key if cap else None, "field_map": m.field_map, "arg_template": m.arg_template,
            "status": m.status, "score": m.score, "reasons": m.reasons, "approved_by": m.approved_by,
            "approved_at": m.approved_at}


# --- connections ---------------------------------------------------------------------------

class ConnectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str
    config: dict = Field(default_factory=dict)


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    try:
        return _conn_out(db, service.create_connection(db, who, body.name, body.type, body.config))
    except CapabilityError as e:
        raise _http(e) from e


@router.get("/connections")
def list_connections(db: Session = Depends(get_db), _: Principal = Depends(admin)):
    return [_conn_out(db, c) for c in db.scalars(select(Connection).order_by(Connection.id))]


class ActiveIn(BaseModel):
    active: bool


@router.patch("/connections/{conn_id}")
def set_active(conn_id: int, body: ActiveIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    c = _conn(db, conn_id)
    c.active = body.active
    audit(db, who, "connection_active_changed", c.slug, {"active": body.active})
    db.commit()
    return _conn_out(db, c)


@router.post("/connections/{conn_id}/health")
def health(conn_id: int, db: Session = Depends(get_db), _: Principal = Depends(admin)):
    c = _conn(db, conn_id)
    return {**service.check_health(db, c), "connection": _conn_out(db, c)}


@router.post("/connections/{conn_id}/discover")
def discover(conn_id: int, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    c = _conn(db, conn_id)
    if not c.active:
        raise HTTPException(409, "The connection is not active")
    try:
        return service.discover(db, who, c)
    except CapabilityError as e:
        raise _http(e) from e


# --- capabilities --------------------------------------------------------------------------

@router.get("/capabilities")
def list_capabilities(q: str | None = None, connection_id: int | None = None, risk: str | None = None,
                      lifecycle: str | None = None, db: Session = Depends(get_db), _: Principal = Depends(admin)):
    return [_cap_out(c) for c in service.search(db, q, connection_id, risk, lifecycle)]


@router.get("/capabilities/{cap_id}")
def get_capability(cap_id: int, db: Session = Depends(get_db), _: Principal = Depends(admin)):
    c = _cap(db, cap_id)
    versions = db.scalars(select(CapabilityVersion).where(CapabilityVersion.capability_id == c.id)
                          .order_by(CapabilityVersion.version.desc()))
    maps = db.scalars(select(KpiMapping).where(KpiMapping.capability_id == c.id).order_by(KpiMapping.id))
    return {**_cap_out(c), "input_schema": c.input_schema, "output_schema": c.output_schema,
            "kpis_using_it": service.dependents(db, c),
            "versions": [{"version": v.version, "validated": v.validated, "risk": v.risk,
                          "schema_hash": v.schema_hash[:12], "created_at": v.created_at,
                          "published": v.version == c.published_version} for v in versions],
            "mappings": [_mapping_out(m, c) for m in maps]}


class ValidateIn(BaseModel):
    sample_args: dict | None = None


@router.post("/capabilities/{cap_id}/validate")
def validate(cap_id: int, body: ValidateIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    c = _cap(db, cap_id)
    return {"validation": service.validate_capability(db, who, c, body.sample_args), "capability": _cap_out(c)}


class TestIn(BaseModel):
    args: dict = Field(default_factory=dict)


@router.post("/capabilities/{cap_id}/test")
def test_call(cap_id: int, body: TestIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    """Try a READ capability with sample arguments. Anything that could change something is refused."""
    c = _cap(db, cap_id)
    if c.risk != "read":
        raise HTTPException(403, "Only read capabilities can be test-called")
    conn = _conn(db, c.connection_id)
    try:
        out = invoke(db, conn, c.implementation, c.input_schema, body.args)
    except CapabilityError as e:
        raise _http(e) from e
    audit(db, who, "capability_test_call", c.key)
    db.commit()
    text = json.dumps(out, default=str)
    return {"output": out} if len(text) <= MAX_TEST_OUTPUT_CHARS else {"truncated": True, "preview": text[:2000]}


class RiskIn(BaseModel):
    risk: str
    reason: str = Field(min_length=1, max_length=300)


@router.post("/capabilities/{cap_id}/risk")
def change_risk(cap_id: int, body: RiskIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    try:
        return _cap_out(service.set_risk(db, who, _cap(db, cap_id), body.risk, body.reason))
    except ConfigError as e:
        raise _http(e) from e


class PermissionsIn(BaseModel):
    roles: list[str] = Field(default_factory=list)


@router.post("/capabilities/{cap_id}/permissions")
def set_permissions(cap_id: int, body: PermissionsIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    """Which roles may use this capability through the Copilot (admins always may). Group-wide users only."""
    c = _cap(db, cap_id)
    roles = sorted(set(body.roles) | {"admin"})
    if set(roles) - {"admin", "editor", "viewer"}:
        raise HTTPException(422, "roles must be admin, editor or viewer")
    if c.risk != "read" and roles != ["admin"]:
        raise HTTPException(422, "Only read capabilities can be shared beyond admins")
    c.permissions = roles
    audit(db, who, "capability_permissions", c.key, {"roles": roles})
    db.commit()
    return _cap_out(c)


@router.post("/capabilities/{cap_id}/deprecate")
def deprecate(cap_id: int, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    c = service.deprecate(db, who, _cap(db, cap_id))
    return {**_cap_out(c), "kpis_using_it": service.dependents(db, c)}


# --- KPI mappings --------------------------------------------------------------------------

@router.get("/kpi-mappings")
def list_mappings(status: str | None = None, db: Session = Depends(get_db), _: Principal = Depends(admin)):
    q = select(KpiMapping, Capability).join(Capability, Capability.id == KpiMapping.capability_id)
    if status:
        q = q.where(KpiMapping.status == status)
    return [_mapping_out(m, c) for m, c in db.execute(q.order_by(KpiMapping.kpi_key, KpiMapping.score.desc()))]


@router.post("/kpi-mappings/recommend")
def recommend(db: Session = Depends(get_db), who: Principal = Depends(admin)):
    created = recommender.recommend(db, who)
    audit(db, who, "kpi_mappings_recommended", None, {"count": len(created)})
    db.commit()
    return {"recommended": len(created),
            "mappings": [_mapping_out(m, db.get(Capability, m.capability_id)) for m in created]}


class MappingPatch(BaseModel):
    field_map: dict[str, str] | None = None
    arg_template: dict[str, str] | None = None


@router.patch("/kpi-mappings/{mapping_id}")
def edit_mapping(mapping_id: int, body: MappingPatch, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    m = db.get(KpiMapping, mapping_id)
    if m is None:
        raise HTTPException(404, "Mapping not found")
    if m.status != "recommended":
        raise HTTPException(409, "Only an open recommendation can be edited")
    if body.field_map is not None:
        m.field_map = body.field_map
    if body.arg_template is not None:
        m.arg_template = body.arg_template
    audit(db, who, "kpi_mapping_edited", f"{m.kpi_key}#{m.id}")
    db.commit()
    return _mapping_out(m)


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


@router.post("/kpi-mappings/{mapping_id}/reject")
def reject_mapping(mapping_id: int, body: RejectIn, db: Session = Depends(get_db), who: Principal = Depends(admin)):
    m = db.get(KpiMapping, mapping_id)
    if m is None:
        raise HTTPException(404, "Mapping not found")
    if m.status not in ("recommended", "approved"):
        raise HTTPException(409, f"A {m.status} mapping cannot be rejected")
    was = m.status
    m.status = "rejected"
    audit(db, who, "kpi_mapping_rejected", f"{m.kpi_key}#{m.id}", {"was": was, "reason": body.reason})
    db.commit()
    return _mapping_out(m)
