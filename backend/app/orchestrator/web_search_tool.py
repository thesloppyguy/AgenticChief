"""Anthropic native server-side web search tool."""
from __future__ import annotations

from typing import Any

from app.core.config import settings

WEB_SEARCH_TOOL_NAME = "web_search"


def build_web_search_tool(*, max_uses: int | None = None) -> dict[str, Any] | None:
    if not settings.enable_web_search:
        return None
    tool: dict[str, Any] = {
        "type": "web_search_20250305",
        "name": WEB_SEARCH_TOOL_NAME,
        "max_uses": max_uses if max_uses is not None else settings.web_search_max_uses,
    }
    if settings.web_search_allowed_domains:
        tool["allowed_domains"] = settings.web_search_allowed_domains
    if settings.web_search_blocked_domains:
        tool["blocked_domains"] = settings.web_search_blocked_domains
    return tool
