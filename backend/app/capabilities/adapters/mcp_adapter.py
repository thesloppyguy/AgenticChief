"""MCP connection adapter, on the official SDK (Streamable HTTP). Tools are discovered with tools/list
(paginated) and called with tools/call. Our pipeline is synchronous, so each operation runs its own
short event loop."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from ..types import DiscoveredTool, DiscoveryError, InvocationError
from ..urlguard import check_url

MAX_TOOLS = 1000
MAX_RESULT_CHARS = 200_000


@asynccontextmanager
async def _open_http(config: dict, headers: dict):
    check_url(config["url"])
    http = httpx2.AsyncClient(headers=headers, timeout=config.get("timeout_s", 30))
    async with http, Client(streamable_http_client(config["url"], http_client=http)) as client:
        yield client


# The one seam tests replace, to talk to an in-process server instead of the network.
_open: Callable[[dict, dict], AbstractAsyncContextManager] = _open_http


def classify_risk(annotations) -> str:
    """From the tool's own hints. The MCP defaults are cautious: a tool that does not say it is read-only
    may be destructive, so it is treated that way until an admin reclassifies it."""
    if annotations is not None:
        if getattr(annotations, "read_only_hint", None) is True:
            return "read"
        if getattr(annotations, "destructive_hint", None) is False:
            return "internal_write"
    return "destructive"


async def _discover(config: dict, headers: dict) -> list[DiscoveredTool]:
    tools, cursor = [], None
    async with _open(config, headers) as client:
        while True:
            res = await client.list_tools(cursor=cursor)
            tools.extend(res.tools)
            cursor = res.next_cursor
            if not cursor or len(tools) >= MAX_TOOLS:
                break
    return [DiscoveredTool(
        name=t.name, description=(t.description or t.title or "").strip(),
        input_schema=t.input_schema or {"type": "object", "properties": {}},
        output_schema=t.output_schema, implementation={"type": "mcp", "tool": t.name},
        risk=classify_risk(t.annotations)) for t in tools]


async def _call(config: dict, headers: dict, tool: str, args: dict) -> dict:
    async with _open(config, headers) as client:
        res = await client.call_tool(tool, args)
    if res.is_error:  # a tool-side failure arrives as a result, not an exception
        raise InvocationError("the tool reported an error")
    if isinstance(res.structured_content, dict):
        return res.structured_content
    text = "".join(getattr(c, "text", "") for c in res.content)[:MAX_RESULT_CHARS]
    try:
        parsed = json.loads(text)
    except ValueError:
        return {"text": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _run(coro, timeout_s: float):
    return asyncio.run(asyncio.wait_for(coro, timeout_s))


def discover(config: dict, headers: dict) -> list[DiscoveredTool]:
    try:
        return _run(_discover(config, headers), config.get("timeout_s", 30) * 2)
    except Exception as e:
        raise DiscoveryError(f"MCP discovery failed ({type(e).__name__})") from e


def call(config: dict, headers: dict, tool: str, args: dict) -> dict:
    try:
        return _run(_call(config, headers, tool, args), config.get("timeout_s", 30) * 2)
    except InvocationError:
        raise
    except Exception as e:
        raise InvocationError(f"MCP call failed ({type(e).__name__})") from e
