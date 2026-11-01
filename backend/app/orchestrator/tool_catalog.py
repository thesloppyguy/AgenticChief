"""Catalog of tools the Executive can use: builtin, MCP, and saved custom."""
from __future__ import annotations

from typing import Any, Literal

from app.copilot.tools import TOOLS as SCORECARD_TOOLS
from app.orchestrator import saved_tools, skills_tools
from app.orchestrator.mcp_gateway import MCP_GATEWAY_TOOLS, get_active_gateway
from app.orchestrator.router import SPECIALIST_TOOLS

Source = Literal["builtin", "mcp", "custom"]

_SCORECARD_NAMES = {t["name"] for t in SCORECARD_TOOLS if t["name"] != "delegate"}


def _item(
    *,
    name: str,
    description: str,
    source: Source,
    group: str,
    enabled: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "description": description or "",
        "source": source,
        "group": group,
        "enabled": enabled,
    }
    if extra:
        row.update(extra)
    return row


def builtin_tools() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for t in SPECIALIST_TOOLS:
        items.append(
            _item(
                name=t["name"],
                description=t.get("description") or "",
                source="builtin",
                group="Specialists",
            )
        )
    for t in skills_tools.SKILL_TOOLS:
        items.append(
            _item(
                name=t["name"],
                description=t.get("description") or "",
                source="builtin",
                group="Skills",
            )
        )
    from app.orchestrator import org_tools
    from app.workforce import tools as workforce_tools

    for t in org_tools.ORG_TOOLS:
        items.append(
            _item(
                name=t["name"],
                description=t.get("description") or "",
                source="builtin",
                group="Org",
            )
        )
    for t in workforce_tools.WORKFORCE_TOOLS:
        items.append(
            _item(
                name=t["name"],
                description=t.get("description") or "",
                source="builtin",
                group="Workforce",
            )
        )
    for t in SCORECARD_TOOLS:
        if t["name"] not in _SCORECARD_NAMES:
            continue
        items.append(
            _item(
                name=t["name"],
                description=t.get("description") or "",
                source="builtin",
                group="Scorecard",
            )
        )
    for t in MCP_GATEWAY_TOOLS:
        items.append(
            _item(
                name=t["name"],
                description=t.get("description") or "",
                source="builtin",
                group="MCP gateway",
            )
        )
    items.sort(key=lambda x: (x["group"], x["name"]))
    return items


def mcp_tools() -> list[dict[str, Any]]:
    gateway = get_active_gateway()
    if gateway is None:
        return []
    items: list[dict[str, Any]] = []
    for meta in gateway._tools.values():  # noqa: SLF001 — catalog read of indexed tools
        items.append(
            _item(
                name=meta["name"],
                description=meta.get("description") or "",
                source="mcp",
                group=meta.get("server") or "MCP",
                extra={"server": meta.get("server")},
            )
        )
    items.sort(key=lambda x: (x["group"], x["name"]))
    return items


def custom_tools() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for t in saved_tools.list_tools():
        items.append(
            _item(
                name=t.name,
                description=t.description,
                source="custom",
                group="Custom",
                enabled=t.enabled,
                extra={
                    "active_version": t.active_version,
                    "workflow_approved_version": t.workflow_approved_version,
                    "kind": t.kind,
                },
            )
        )
    items.sort(key=lambda x: x["name"])
    return items


def catalog() -> dict[str, Any]:
    builtin = builtin_tools()
    mcp = mcp_tools()
    custom = custom_tools()
    return {
        "builtin": builtin,
        "mcp": mcp,
        "custom": custom,
        "counts": {
            "builtin": len(builtin),
            "mcp": len(mcp),
            "custom": len(custom),
            "total": len(builtin) + len(mcp) + len(custom),
        },
    }
