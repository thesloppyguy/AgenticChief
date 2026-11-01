"""Custom/saved tools API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import Principal, require_admin
from app.orchestrator import saved_tools

router = APIRouter(prefix="/saved-tools", tags=["saved-tools"])


class EnableBody(BaseModel):
    enabled: bool


class RollbackBody(BaseModel):
    version: int


class ApproveBody(BaseModel):
    version: int | None = None


class UpsertBody(BaseModel):
    name: str
    description: str
    code: str
    called_tools: list[str] | None = None
    kind: str = "script"


@router.get("")
def list_tools(_who: Principal = Depends(require_admin)) -> list[dict[str, Any]]:
    return [t.model_dump() for t in saved_tools.list_tools()]


@router.get("/{name}")
def get_tool(name: str, _who: Principal = Depends(require_admin)) -> dict[str, Any]:
    tool = saved_tools.get_tool(name)
    if tool is None:
        raise HTTPException(404, "Tool not found")
    return tool


@router.post("")
def upsert_tool(body: UpsertBody, _who: Principal = Depends(require_admin)) -> dict[str, Any]:
    version = saved_tools.upsert_version(
        body.name,
        description=body.description,
        code=body.code,
        called_tools=body.called_tools,
        kind=body.kind,
    )
    return {"name": body.name, "version": version}


@router.post("/{name}/enable")
def enable_tool(
    name: str, body: EnableBody, _who: Principal = Depends(require_admin)
) -> dict[str, Any]:
    if not saved_tools.set_enabled(name, body.enabled):
        raise HTTPException(404, "Tool not found")
    return saved_tools.get_tool(name) or {}


@router.post("/{name}/rollback")
def rollback_tool(
    name: str, body: RollbackBody, _who: Principal = Depends(require_admin)
) -> dict[str, Any]:
    if not saved_tools.rollback(name, body.version):
        raise HTTPException(404, "Tool or version not found")
    return saved_tools.get_tool(name) or {}


@router.post("/{name}/approve-workflow")
def approve_tool(
    name: str, body: ApproveBody, _who: Principal = Depends(require_admin)
) -> dict[str, Any]:
    if not saved_tools.approve_for_workflows(name, body.version):
        raise HTTPException(404, "Tool not found")
    return saved_tools.get_tool(name) or {}
