from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.copilot import get_anthropic
from app.assets import service
from app.assets.definitions import MODELS
from app.assets.service import AssetError
from app.core.security import Principal, Role, get_principal, require_admin, require_editor
from app.db.models import Asset, AssetVersion
from app.db.session import get_db
from app.services.scorecard import current_period


def _http(e: AssetError) -> HTTPException:
    return HTTPException(e.status, e.message)


def _author(who: Principal = Depends(require_editor)) -> Principal:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    return who


def _admin(who: Principal = Depends(require_admin)) -> Principal:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    return who


class CreateIn(BaseModel):
    key: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    definition: dict


class VersionIn(BaseModel):
    definition: dict


def make_router(kind: str) -> APIRouter:
    router = APIRouter(prefix=f"/{kind}s")

    def _summary(db: Session, a: Asset, privileged: bool) -> dict:
        # Everyone sees the published contract. An author with nothing published yet sees the latest draft,
        # so they can build and try it (a published skill keeps showing what users actually get).
        shown_version = a.published_version or (a.version if privileged else None)
        row = service.version_row(db, a, shown_version) if shown_version else None
        shown = row.definition if row else None
        return {"id": a.id, "key": a.key, "name": a.name, "description": a.description, "lifecycle": a.lifecycle,
                "version": a.version, "published_version": a.published_version, "builtin": a.builtin,
                "tools": (shown or {}).get("tools", []), "permissions": (shown or {}).get("permissions", []),
                "inputs": (shown or {}).get("inputs") if kind == "skill" else None,
                "model": (shown or {}).get("model") if kind == "agent" else None}

    @router.get("")
    def list_assets(db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
        privileged = who.role in (Role.ADMIN, Role.EDITOR) and who.company_ids is None
        rows = db.scalars(select(Asset).where(Asset.kind == kind).order_by(Asset.builtin.desc(), Asset.name))
        out = []
        for a in rows:
            if not privileged:  # authors see everything they manage; everyone else only what they may use
                if a.deprecated or a.published_version is None:
                    continue
                live = MODELS[kind](**service.version_row(db, a, a.published_version).definition)
                if who.role.value not in live.permissions:
                    continue
            out.append(_summary(db, a, privileged))
        return out

    @router.get("/{key}")
    def detail(key: str, db: Session = Depends(get_db), who: Principal = Depends(get_principal)):
        try:
            a = service.get(db, kind, key)
        except AssetError as e:
            raise _http(e) from e
        privileged = who.role in (Role.ADMIN, Role.EDITOR) and who.company_ids is None
        if a.published_version is None and not privileged:
            raise HTTPException(404, f"{kind} not found")
        versions = list(db.scalars(select(AssetVersion).where(AssetVersion.asset_id == a.id).order_by(AssetVersion.version.desc())))
        out = _summary(db, a, privileged)
        if privileged:
            out["definition"] = versions[0].definition
            out["validation"] = a.validation
            out["versions"] = [{"version": v.version, "validated": v.validated, "eval_passed": v.eval_passed,
                                "published": v.version == a.published_version, "created_by": v.created_by,
                                "eval_results": v.eval_results} for v in versions]
        return out

    @router.post("", status_code=201)
    def create(body: CreateIn, db: Session = Depends(get_db), who: Principal = Depends(_author)):
        try:
            a = service.create(db, who, kind, body.key, body.name, body.description, body.definition)
        except AssetError as e:
            raise _http(e) from e
        return _summary(db, a, True)

    @router.post("/{key}/versions", status_code=201)
    def add_version(key: str, body: VersionIn, db: Session = Depends(get_db), who: Principal = Depends(_author)):
        try:
            a = service.new_version(db, who, service.get(db, kind, key), body.definition)
        except AssetError as e:
            raise _http(e) from e
        return _summary(db, a, True)

    @router.post("/{key}/validate")
    def validate(key: str, db: Session = Depends(get_db), who: Principal = Depends(_author)):
        try:
            a = service.get(db, kind, key)
        except AssetError as e:
            raise _http(e) from e
        return {"validation": service.validate(db, who, a), "lifecycle": a.lifecycle}

    @router.post("/{key}/evals")
    def evals(key: str, period: str | None = None, db: Session = Depends(get_db), who: Principal = Depends(_author),
              client=Depends(get_anthropic)):
        """Runs the eval cases against the live model, so it needs a configured API key."""
        try:
            return service.run_evals(db, who, service.get(db, kind, key), client, period or current_period())
        except AssetError as e:
            raise _http(e) from e

    @router.post("/{key}/deprecate")
    def deprecate(key: str, db: Session = Depends(get_db), who: Principal = Depends(_admin)):
        try:
            a = service.deprecate(db, who, service.get(db, kind, key))
        except AssetError as e:
            raise _http(e) from e
        return _summary(db, a, True)

    return router


skills_router, agents_router = make_router("skill"), make_router("agent")
__all__ = ["MODELS", "agents_router", "skills_router"]
