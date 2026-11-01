"""Connector / MCP setup status (OpenExecutive-style)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.core.security import Principal, require_admin
from app.orchestrator.mcp_gateway import get_active_gateway

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status")
def setup_status(_who: Principal = Depends(require_admin)) -> dict[str, Any]:
    settings = get_settings()
    path = Path(settings.mcp_servers_path)
    servers: list[dict[str, Any]] = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for name, cfg in (raw.get("mcpServers") or {}).items():
                if name.startswith("_") or not isinstance(cfg, dict):
                    continue
                servers.append(
                    {
                        "name": name,
                        "transport": "url" if "url" in cfg else "stdio",
                        "command": cfg.get("command"),
                        "url": cfg.get("url"),
                    }
                )
        except (OSError, json.JSONDecodeError) as e:
            return {
                "mcp_enabled": settings.mcp_enabled,
                "mcp_servers_path": str(path),
                "error": str(e),
                "servers": [],
                "gateway": {"ready": False, "tool_count": 0},
            }
    gateway = get_active_gateway()
    return {
        "mcp_enabled": settings.mcp_enabled,
        "mcp_servers_path": str(path),
        "anthropic_configured": bool(settings.anthropic_api_key),
        "vector_store_path": settings.vector_store_path,
        "company_dir": settings.company_dir,
        "servers": servers,
        "gateway": {
            "ready": bool(gateway and gateway.ready),
            "tool_count": len(gateway._tools) if gateway else 0,
            "connected_servers": list(gateway._sessions.keys()) if gateway else [],
        },
    }
