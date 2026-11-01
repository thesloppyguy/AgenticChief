"""MCP gateway: launch servers from mcp_servers.json over stdio (MCP 2.x).

Simplified OpenExecutive-style gateway: discovers and calls tools from
configured child MCP servers without the extensible-mcp subprocess.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

MCP_GATEWAY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_tools",
        "description": (
            "Discover external MCP tools by describing what you need. "
            "Always call this before call_tool when you don't know the exact name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "call_tool",
        "description": "Invoke a discovered MCP tool by its exact namespaced name (server__tool).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["name"],
        },
    },
]

_active: MCPGateway | None = None


def get_active_gateway() -> MCPGateway | None:
    return _active


def set_active_gateway(gateway: MCPGateway | None) -> None:
    global _active
    _active = gateway


def _load_servers(config_path: Path) -> dict[str, dict[str, Any]]:
    if not config_path.exists():
        return {}
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers") if isinstance(raw, dict) else None
    if not isinstance(servers, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in servers.items():
        if name.startswith("_") or not isinstance(cfg, dict):
            continue
        if "command" in cfg or "url" in cfg:
            out[name] = cfg
    return out


def _deny_patterns(config_path: Path) -> list[str]:
    if not config_path.exists():
        return []
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    filters = raw.get("filters") if isinstance(raw, dict) else None
    ac = filters.get("access_control") if isinstance(filters, dict) else None
    patterns = ac.get("deny_patterns") if isinstance(ac, dict) else None
    return [p for p in patterns or [] if isinstance(p, str)]


def _denied(tool_name: str, patterns: list[str]) -> bool:
    import fnmatch

    return any(fnmatch.fnmatch(tool_name, p) for p in patterns)


class MCPGateway:
    """Owns stdio MCP client sessions for configured servers."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or settings.mcp_servers_path)
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}
        self._tools: dict[str, dict[str, Any]] = {}  # namespaced name -> meta
        self._deny = _deny_patterns(self.config_path)

    @property
    def ready(self) -> bool:
        return bool(self._sessions)

    async def start(self) -> None:
        if self._stack is not None:
            return
        servers = _load_servers(self.config_path)
        if not servers:
            logger.info("MCP gateway: no servers in %s", self.config_path)
            return
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for name, cfg in servers.items():
            if "url" in cfg:
                logger.warning("MCP gateway: skipping HTTP server %s (stdio-only in this port)", name)
                continue
            command = cfg.get("command")
            if not command:
                continue
            args = list(cfg.get("args") or [])
            env = {**os.environ}
            for k, v in (cfg.get("env") or {}).items():
                if isinstance(v, str) and v.startswith("$"):
                    env[k] = os.environ.get(v[1:], "")
                elif isinstance(v, str):
                    env[k] = v
            try:
                params = StdioServerParameters(command=command, args=args, env=env)
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=60)
                self._sessions[name] = session
                await self._index_tools(name, session)
                logger.info("MCP gateway: connected %s (%d tools)", name, sum(
                    1 for t in self._tools if t.startswith(f"{name}__")
                ))
            except Exception:
                logger.exception("MCP gateway: failed to start server %s", name)

    async def _index_tools(self, server: str, session: Any) -> None:
        cursor = None
        while True:
            result = await session.list_tools(cursor=cursor)
            for tool in result.tools:
                ns = f"{server}__{tool.name}"
                if _denied(ns, self._deny) or _denied(tool.name, self._deny):
                    continue
                self._tools[ns] = {
                    "name": ns,
                    "server": server,
                    "tool": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
                }
            cursor = getattr(result, "nextCursor", None) or getattr(result, "next_cursor", None)
            if not cursor:
                break

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._sessions.clear()
        self._tools.clear()

    async def search_tools(self, tool_input: dict[str, Any]) -> str:
        query = (tool_input.get("query") or "").lower()
        limit = int(tool_input.get("limit") or 8)
        scored: list[tuple[int, dict[str, Any]]] = []
        for meta in self._tools.values():
            hay = f"{meta['name']} {meta['description']}".lower()
            score = sum(1 for token in query.split() if token and token in hay)
            if score or not query:
                scored.append((score, meta))
        scored.sort(key=lambda x: (-x[0], x[1]["name"]))
        hits = [
            {
                "name": m["name"],
                "description": m["description"],
                "input_schema": m["input_schema"],
            }
            for _, m in scored[:limit]
        ]
        return json.dumps({"tools": hits}, ensure_ascii=False)

    async def call_tool(self, tool_input: dict[str, Any]) -> str:
        name = tool_input.get("name") or ""
        arguments = tool_input.get("arguments") or {}
        meta = self._tools.get(name)
        if meta is None:
            return json.dumps({"error": f"Unknown tool '{name}'. Call search_tools first."})
        if _denied(name, self._deny):
            return json.dumps({"error": f"Tool '{name}' is denied by policy."})
        session = self._sessions.get(meta["server"])
        if session is None:
            return json.dumps({"error": f"Server '{meta['server']}' is not connected."})
        try:
            result = await asyncio.wait_for(
                session.call_tool(meta["tool"], arguments),
                timeout=settings.mcp_tool_timeout_s,
            )
            # Normalize content blocks to text/json
            parts: list[str] = []
            for block in getattr(result, "content", []) or []:
                text = getattr(block, "text", None)
                if text is not None:
                    parts.append(text)
                else:
                    parts.append(str(block))
            payload: dict[str, Any] = {"result": "\n".join(parts)}
            if getattr(result, "isError", False) or getattr(result, "is_error", False):
                payload["error"] = True
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.exception("MCP call_tool %s failed", name)
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


async def boot_gateway() -> MCPGateway | None:
    if not settings.mcp_enabled:
        set_active_gateway(None)
        return None
    gateway = MCPGateway()
    try:
        await gateway.start()
    except Exception:
        logger.exception("MCP gateway boot failed")
        set_active_gateway(None)
        return None
    set_active_gateway(gateway)
    return gateway
