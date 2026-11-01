"""Tool catalog API — builtin, MCP, and custom/saved tools."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import Principal, require_admin
from app.orchestrator import tool_catalog

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/catalog")
def get_catalog(_who: Principal = Depends(require_admin)) -> dict[str, Any]:
    return tool_catalog.catalog()
