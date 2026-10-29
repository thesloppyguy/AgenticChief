"""Single orchestrator loop on the Anthropic SDK with native tool use and prompt caching."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.capabilities import copilot_tools
from app.capabilities.copilot_tools import CapTool
from app.core.config import settings
from app.core.security import Principal

from .prompts import COPILOT_PERSONA
from .tools import TOOLS, run_tool

MAX_TOOL_ROUNDS = 6
HISTORY_TURNS = 20


def _system(extra: str | None = None) -> list[dict]:
    # The persona is a frozen constant and always first. A skill's or agent's instructions are stable per
    # asset version, so they are cached as their own block after it.
    blocks = [{"type": "text", "text": COPILOT_PERSONA, "cache_control": {"type": "ephemeral"}}]
    if extra:
        blocks.append({"type": "text", "text": extra, "cache_control": {"type": "ephemeral"}})
    return blocks


def _tools(names: list[str] | None = None, cap_tools: dict[str, CapTool] | None = None) -> list[dict]:
    chosen = [dict(t) for t in TOOLS if names is None or t["name"] in names]
    chosen += [dict(c.definition) for c in (cap_tools or {}).values()]
    chosen.sort(key=lambda t: t["name"])  # a stable, name-sorted array keeps the prompt cache valid
    if chosen:
        chosen[-1]["cache_control"] = {"type": "ephemeral"}
    return chosen


def _run_one(db: Session, who: Principal, name: str, args: dict, session_id: int | None) -> dict:
    out = run_tool(db, who, name, args, session_id)
    audit(db, who, "copilot_tool", name, {"input": args})
    return out


def _run_cap(db: Session, who: Principal, tool: CapTool, args: dict) -> dict:
    return copilot_tools.run(db, who, tool, args)


async def chat_turn(
    client: Any, db: Session, who: Principal, history: list[dict], user_message: str, period: str,
    session_id: int | None = None, extra_system: str | None = None,
    tool_names: list[str] | None = None, model: str | None = None, memory_block: str | None = None,
    cap_tools: dict[str, CapTool] | None = None,
) -> AsyncIterator[dict]:
    """Yields {'type': 'chunk'|'tool', ...} events; caller persists and emits 'done'."""
    # Dynamic context goes in the user turn, never the cached system prompt.
    messages = history[-HISTORY_TURNS * 2:] + [
        {"role": "user", "content": (f"{memory_block}\n" if memory_block else "")
                                    + f"<context>Default period: {period}</context>\n{user_message}"}
    ]
    for _ in range(MAX_TOOL_ROUNDS):
        async with client.messages.stream(
            model=model or settings.default_model, max_tokens=2048, system=_system(extra_system),
            tools=_tools(tool_names, cap_tools), messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "chunk", "content": text}
            final = await stream.get_final_message()
        if final.stop_reason != "tool_use":
            return
        messages.append({"role": "assistant", "content": [b.model_dump() for b in final.content]})
        results = []
        for block in (b for b in final.content if b.type == "tool_use"):
            if cap_tools and block.name in cap_tools:
                out = await asyncio.to_thread(_run_cap, db, who, cap_tools[block.name], dict(block.input))
            elif tool_names is not None and block.name not in tool_names:  # defence in depth: it was never offered
                out = {"error": "that tool is not available here"}
            else:
                # Tools hit the database (scorecards for 88 companies): keep that off the event loop.
                out = await asyncio.to_thread(_run_one, db, who, block.name, dict(block.input), session_id)
            yield {"type": "tool", "name": block.name}
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})
    yield {"type": "chunk", "content": "\n\n(Stopped: too many tool steps.)"}
