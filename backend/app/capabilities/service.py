"""Connections and the capability registry: configure -> discover -> normalize -> validate -> publish."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.alerts import engine as alerts_engine
from app.audit.logger import audit
from app.core.security import Principal
from app.db.models import Capability, CapabilityVersion, Connection, KpiMapping
from app.reports.integrity import canonical_hash

from .adapters import function_adapter, mcp_adapter, openapi_adapter
from .auth import auth_headers, validate_auth
from .invoke import invoke
from .types import RISKS, CapabilityError, ConfigError, DiscoveredTool, DiscoveryError
from .urlguard import check_url

TYPES = ("mcp", "api", "function")


def _now() -> datetime:
    return datetime.now(UTC)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "connection"


# --- connections ---------------------------------------------------------------------------

def _clean_config(type_: str, config: dict) -> dict:
    cfg: dict = {"auth": validate_auth(config.get("auth")), "timeout_s": float(config.get("timeout_s", 30))}
    if not 1 <= cfg["timeout_s"] <= 120:
        raise ConfigError("timeout_s must be between 1 and 120")
    if type_ == "mcp":
        if not config.get("url"):
            raise ConfigError("url is required for an MCP connection")
        check_url(config["url"])
        cfg["url"] = config["url"]
    elif type_ == "api":
        if not (config.get("spec") or config.get("spec_url")):
            raise ConfigError("an OpenAPI document (spec or spec_url) is required")
        spec = None
        if config.get("spec"):
            spec = openapi_adapter.load_spec(config["spec"])
            cfg["spec"] = spec
        if config.get("spec_url"):
            check_url(config["spec_url"])
            cfg["spec_url"] = config["spec_url"]
        base = config.get("server_url") or (openapi_adapter.server_url(spec, config.get("spec_url")) if spec else None)
        if base:
            check_url(base)
            cfg["server_url"] = base
    elif type_ == "function":
        cfg = {"auth": {"type": "none"}, "timeout_s": 30.0}
    return cfg


def create_connection(db: Session, who: Principal, name: str, type_: str, config: dict) -> Connection:
    if type_ not in TYPES:
        raise ConfigError("type must be mcp, api or function")
    slug = slugify(name)
    if db.scalar(select(Connection.id).where(Connection.slug == slug)):
        raise ConfigError("a connection with that name already exists")
    conn = Connection(slug=slug, name=name.strip()[:120], type=type_, config=_clean_config(type_, config),
                      created_by=who.user_id)
    db.add(conn)
    audit(db, who, "connection_created", slug, {"type": type_})
    db.commit()
    return conn


def public_config(conn: Connection) -> dict:
    """What the API may show: no secret values (there are none stored), and the spec is summarized."""
    c = dict(conn.config)
    if "spec" in c:
        c["spec"] = f"<OpenAPI document, {len(c['spec'].get('paths', {}))} paths>"
    return c


def check_health(db: Session, conn: Connection) -> dict:
    ok, detail = True, "ok"
    try:
        if conn.type == "mcp":
            n = len(mcp_adapter.discover(conn.config, auth_headers(conn.config.get("auth"))))
            detail = f"{n} tools offered"
        elif conn.type == "api":
            import httpx

            base = conn.config.get("server_url")
            if not base:
                raise ConfigError("no server_url")
            check_url(base)
            status = httpx.get(base, headers=auth_headers(conn.config.get("auth")), timeout=conn.config["timeout_s"],
                               follow_redirects=False).status_code
            ok, detail = status < 500, f"HTTP {status}"
    except CapabilityError as e:
        ok, detail = False, str(e)[:200]
    except Exception as e:  # noqa: BLE001 - any failure to reach it is "unhealthy"; type only
        ok, detail = False, type(e).__name__
    conn.health_status, conn.health_checked_at, conn.health_detail = "healthy" if ok else "unhealthy", _now(), detail
    db.commit()
    return {"healthy": ok, "detail": detail}


# --- discovery and normalization -----------------------------------------------------------

def _discover_tools(conn: Connection) -> list[DiscoveredTool]:
    if conn.type == "function":
        return function_adapter.discover()
    headers = auth_headers(conn.config.get("auth"))
    if conn.type == "mcp":
        return mcp_adapter.discover(conn.config, headers)
    spec = conn.config.get("spec")
    if spec is None:
        spec = openapi_adapter.fetch_spec(conn.config["spec_url"], headers, conn.config["timeout_s"])
    return openapi_adapter.parse(spec)


def _definition_hash(t: DiscoveredTool) -> str:
    """The upstream-defined shape. An admin's risk override is deliberately NOT part of it."""
    return canonical_hash({"in": t.input_schema, "out": t.output_schema, "impl": t.implementation, "risk": t.risk})


def lifecycle_of(cap: Capability) -> str:
    if cap.removed:
        return "removed"
    if cap.deprecated:
        return "deprecated"
    if cap.published_version is not None:
        return "published" if cap.published_version == cap.version else "update_pending"
    return "validated" if cap.validated_version == cap.version else "draft"


def _snapshot_version(db: Session, cap: Capability) -> CapabilityVersion:
    v = CapabilityVersion(capability_id=cap.id, version=cap.version, description=cap.description,
                          input_schema=cap.input_schema, output_schema=cap.output_schema,
                          implementation=cap.implementation, risk=cap.risk, schema_hash=cap.schema_hash)
    db.add(v)
    return v


def dependents(db: Session, cap: Capability) -> list[str]:
    """KPIs whose approved mapping runs on this capability."""
    return sorted(db.scalars(select(KpiMapping.kpi_key).where(KpiMapping.capability_id == cap.id,
                                                              KpiMapping.status == "approved")))


def discover(db: Session, who: Principal, conn: Connection) -> dict:
    tools = {t.name: t for t in _discover_tools(conn)}  # raises DiscoveryError
    existing = {c.name: c for c in db.scalars(select(Capability).where(Capability.connection_id == conn.id))}
    summary: dict = {"added": [], "changed": [], "unchanged": [], "removed": [], "impacts": []}

    def impact(cap: Capability, what: str) -> None:
        deps = dependents(db, cap)
        if cap.published_version is not None or deps:
            summary["impacts"].append({"capability": cap.key, "change": what, "kpis": deps})
            alerts_engine._raise(
                db, kind="capability_changed", severity="medium" if deps else "low", company_id=None,
                entity=cap.key, period=_now().strftime("%Y-%m"),
                title=f"{cap.key} {what}" + (f"; affects {', '.join(deps)}" if deps else ""),
                detail={"capability": cap.key, "change": what, "kpis": deps, "version": cap.version},
                dedupe_key=f"capability:{cap.key}:{what}:{cap.version}")

    for name, t in tools.items():
        h = _definition_hash(t)
        cap = existing.get(name)
        if cap is None:
            cap = Capability(connection_id=conn.id, key=f"{conn.slug}.{name}"[:160], name=name[:120],
                             description=t.description, input_schema=t.input_schema, output_schema=t.output_schema,
                             implementation=t.implementation, risk=t.risk, permissions=["admin"], version=1,
                             removed=False, deprecated=False, lifecycle="draft", schema_hash=h)
            db.add(cap)
            db.flush()
            _snapshot_version(db, cap)
            summary["added"].append(cap.key)
            continue
        if cap.removed:
            cap.removed = False
        if h != cap.schema_hash:
            cap.version += 1
            cap.description, cap.input_schema, cap.output_schema = t.description, t.input_schema, t.output_schema
            cap.implementation, cap.schema_hash = t.implementation, h
            cap.risk = cap.risk_override or t.risk
            cap.updated_at = _now()
            _snapshot_version(db, cap)
            summary["changed"].append(cap.key)
            impact(cap, "changed upstream (new version awaiting validation)")
        else:
            if t.description != cap.description:  # wording only: no new version
                cap.description = t.description
                latest = db.scalar(select(CapabilityVersion).where(
                    CapabilityVersion.capability_id == cap.id, CapabilityVersion.version == cap.version))
                if latest:
                    latest.description = t.description
            summary["unchanged"].append(cap.key)
        cap.lifecycle = lifecycle_of(cap)

    for name, cap in existing.items():
        if name not in tools and not cap.removed:
            cap.removed = True
            summary["removed"].append(cap.key)
            impact(cap, "no longer offered by its connection")
        cap.lifecycle = lifecycle_of(cap)

    conn.last_discovered_at = _now()
    audit(db, who, "connection_discovered", conn.slug,
          {k: len(v) for k, v in summary.items()})
    db.commit()
    return summary


# --- review: risk, validation, deprecation --------------------------------------------------

def set_risk(db: Session, who: Principal, cap: Capability, risk: str, reason: str) -> Capability:
    """Reclassify a tool. It becomes a NEW version that must be validated and published again, so the
    change itself goes through the second admin's approval."""
    if risk not in RISKS:
        raise ConfigError(f"risk must be one of {', '.join(RISKS)}")
    if not reason.strip():
        raise ConfigError("a reason is required to reclassify a capability")
    if risk == cap.risk:
        return cap
    cap.risk_override, cap.risk = risk, risk
    cap.version += 1
    cap.updated_at = _now()
    _snapshot_version(db, cap)
    cap.lifecycle = lifecycle_of(cap)
    audit(db, who, "capability_risk_changed", cap.key, {"risk": risk, "reason": reason[:300]})
    db.commit()
    return cap


def validate_capability(db: Session, who: Principal, cap: Capability, sample_args: dict | None = None) -> dict:
    conn = db.get(Connection, cap.connection_id)
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "", skipped: bool = False) -> bool:
        checks.append({"name": name, "ok": ok, "detail": detail, "skipped": skipped})
        return ok

    try:
        Draft202012Validator.check_schema(cap.input_schema)
        if cap.output_schema:
            Draft202012Validator.check_schema(cap.output_schema)
        add("schema_is_valid", True)
    except SchemaError as e:
        add("schema_is_valid", False, e.message[:120])
    impl = cap.implementation
    ok_impl = (impl.get("type") == "function" and impl.get("ref") in function_adapter.FUNCTIONS) or \
              (impl.get("type") == "mcp" and bool(impl.get("tool"))) or \
              (impl.get("type") == "http" and bool(impl.get("method")) and bool(impl.get("path")))
    add("implementation_is_resolvable", ok_impl, "" if ok_impl else "implementation reference is incomplete")
    health = check_health(db, conn)
    add("connection_is_healthy", health["healthy"], health["detail"])
    if sample_args is None:
        add("sample_call", True, "no sample arguments given", skipped=True)
    elif cap.risk != "read":
        add("sample_call", True, "skipped: only read capabilities are called during validation", skipped=True)
    else:
        try:
            out = invoke(db, conn, impl, cap.input_schema, sample_args)
            if cap.output_schema:
                errs = list(Draft202012Validator(cap.output_schema).iter_errors(out))
                add("sample_call", not errs, "output matches the declared schema" if not errs
                    else f"output does not match the declared schema: {errs[0].message[:100]}")
            else:
                add("sample_call", True, "call succeeded (no output schema declared)")
        except CapabilityError as e:
            add("sample_call", False, str(e)[:160])

    ok = all(c["ok"] for c in checks)
    cap.validation = {"checked_at": _now().isoformat(timespec="seconds"), "ok": ok, "version": cap.version,
                      "checks": checks}
    if ok:
        cap.validated_version = cap.version
        v = db.scalar(select(CapabilityVersion).where(CapabilityVersion.capability_id == cap.id,
                                                      CapabilityVersion.version == cap.version))
        if v:
            v.validated = True
    cap.lifecycle = lifecycle_of(cap)
    audit(db, who, "capability_validated", cap.key, {"ok": ok, "version": cap.version})
    db.commit()
    return cap.validation


def deprecate(db: Session, who: Principal, cap: Capability) -> Capability:
    cap.deprecated = True
    cap.lifecycle = lifecycle_of(cap)
    audit(db, who, "capability_deprecated", cap.key, {"kpis": dependents(db, cap)})
    db.commit()
    return cap


def publish_version(db: Session, approver: Principal, cap: Capability, version: int) -> None:
    """Make `version` the one production runs. Publishing an older, previously validated version is a
    rollback. Called only by the approval executor."""
    cap.published_version = version
    cap.lifecycle = lifecycle_of(cap)
    audit(db, approver, "capability_published", cap.key, {"version": version})


# --- reading -------------------------------------------------------------------------------

def search(db: Session, q: str | None = None, connection_id: int | None = None, risk: str | None = None,
           lifecycle: str | None = None, limit: int = 200) -> list[Capability]:
    stmt = select(Capability).order_by(Capability.key).limit(min(limit, 500))
    if q:
        like = f"%{q.lower()}%"
        from sqlalchemy import func

        stmt = stmt.where(or_(func.lower(Capability.key).like(like), func.lower(Capability.description).like(like)))
    if connection_id:
        stmt = stmt.where(Capability.connection_id == connection_id)
    if risk:
        stmt = stmt.where(Capability.risk == risk)
    if lifecycle:
        stmt = stmt.where(Capability.lifecycle == lifecycle)
    return list(db.scalars(stmt))


__all__ = ["DiscoveryError"]
