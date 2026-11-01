"""Executive tool-use loop (OpenExecutive-style, CHRO scorecard tools included)."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.agents.overrides import EXECUTIVE_AGENT_ID, get_override
from app.audit.logger import audit
from app.core.config import settings
from app.core.security import Principal
from app.copilot.tools import TOOLS as SCORECARD_TOOLS
from app.copilot.tools import run_tool
from app.orchestrator import skills_tools
from app.orchestrator.mcp_gateway import MCP_GATEWAY_TOOLS, get_active_gateway
from app.orchestrator.router import SPECIALIST_TOOLS, route_parallel

MAX_TOOL_ROUNDS = 8
HISTORY_TURNS = 20

_SCORECARD_NAMES = {t["name"] for t in SCORECARD_TOOLS if t["name"] != "delegate"}


def _company_stage() -> str:
    try:
        from app.company.profile import load_profile

        return load_profile().stage or ""
    except Exception:
        return ""


def _executive_system(
    system_override: str | list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(system_override, list):
        return system_override
    if isinstance(system_override, str) and system_override.strip():
        return [
            {
                "type": "text",
                "text": system_override,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    from app.prompts.cache_manager import build_system_blocks

    ov = get_override(EXECUTIVE_AGENT_ID)
    return build_system_blocks(
        persona_override=ov.prompt if ov is not None and ov.prompt else None,
        persona_instructions=ov.instructions if ov is not None else None,
        mcp_enabled=get_active_gateway() is not None,
    )


def _tool_defs(
    tools_override: list[str] | list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if tools_override is not None and len(tools_override) == 0:
        return []
    if tools_override is not None and tools_override and isinstance(tools_override[0], dict):
        tools = [dict(t) for t in tools_override]  # type: ignore[arg-type]
        tools.sort(key=lambda t: t.get("name", ""))
        if tools:
            tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        return tools

    from app.orchestrator import document_tools, history_tools, org_tools, reminder_tools, saved_tool_defs
    from app.orchestrator.web_search_tool import build_web_search_tool
    from app.workforce import tools as workforce_tools

    # document_tools owns search_documents; scorecard TOOLS still keeps a copy for run_tool tests.
    scorecard = [
        t for t in SCORECARD_TOOLS
        if t["name"] in _SCORECARD_NAMES and t["name"] != "search_documents"
    ]
    tools = [dict(t) for t in SPECIALIST_TOOLS]
    tools += [dict(t) for t in skills_tools.SKILL_TOOLS]
    tools += [dict(t) for t in document_tools.DOCUMENT_TOOLS]
    tools += [dict(t) for t in saved_tool_defs.SAVED_TOOL_DEFS]
    tools += [dict(t) for t in history_tools.HISTORY_TOOLS]
    tools += [dict(t) for t in reminder_tools.REMINDER_TOOLS]
    tools += [dict(t) for t in org_tools.ORG_TOOLS]
    tools += [dict(t) for t in workforce_tools.WORKFORCE_TOOLS]
    tools += [dict(t) for t in scorecard]
    if get_active_gateway() is not None:
        tools += [dict(t) for t in MCP_GATEWAY_TOOLS]

    if isinstance(tools_override, list) and tools_override and isinstance(tools_override[0], str):
        allow = set(tools_override)
        tools = [t for t in tools if t["name"] in allow]

    # Anthropic rejects the request if any tool name appears twice.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for t in tools:
        name = t.get("name")
        if not isinstance(name, str) or name in seen:
            continue
        seen.add(name)
        unique.append(t)
    tools = unique

    tools.sort(key=lambda t: t["name"])
    if tools:
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

    web = build_web_search_tool()
    if web is not None:
        tools.append(web)
    return tools


def _effective_model(model_override: str | None = None) -> str:
    if model_override:
        return model_override
    ov = get_override(EXECUTIVE_AGENT_ID)
    if ov is not None and ov.model:
        return ov.model
    return settings.default_model


async def _dispatch_tool(
    db: Session,
    who: Principal,
    name: str,
    args: dict[str, Any],
    session_id: int | None,
    client: Any,
    *,
    episodic_context: str = "",
    company_stage: str = "",
) -> Any:
    if name == "consult_specialist":
        results = await route_parallel(
            [args],
            company_stage=company_stage,
            episodic_context=episodic_context,
        )
        return results[0] if results else {"error": "no result"}
    if name == "search_skills":
        return json.loads(skills_tools.handle_search_skills(args))
    if name == "load_skill":
        return json.loads(skills_tools.handle_load_skill(args))
    if name == "search_documents":
        from app.orchestrator import document_tools

        return document_tools.handle_search_documents(db, args)
    if name in ("list_saved_tools", "run_script"):
        from app.orchestrator import saved_tool_defs

        return await saved_tool_defs.handle(
            name,
            args,
            dispatch=lambda n, a: _dispatch_tool(
                db, who, n, a, session_id, client,
                episodic_context=episodic_context,
                company_stage=company_stage,
            ),
        )
    if name == "recall_history":
        from app.orchestrator import history_tools

        return history_tools.handle_recall_history(db, who, args)
    if name in (
        "remind_me",
        "list_open_loops",
        "assign_open_loop",
        "close_open_loop",
    ):
        from app.orchestrator import reminder_tools

        return reminder_tools.handle(db, who, name, args, session_id=session_id)
    if name in ("search_tools", "call_tool"):
        gateway = get_active_gateway()
        if gateway is None:
            return {"error": "MCP gateway is not enabled"}
        if name == "search_tools":
            return json.loads(await gateway.search_tools(args))
        return json.loads(await gateway.call_tool(args))
    if name in ("list_people", "list_goals"):
        from app.orchestrator import org_tools

        return org_tools.dispatch(name, args, db, who)
    from app.workforce.tools import is_workforce_tool

    if is_workforce_tool(name):
        from app.workforce import tools as workforce_tools

        return workforce_tools.dispatch(name, args, db, who)
    if name in _SCORECARD_NAMES:
        return await asyncio.to_thread(
            run_tool, db, who, name, args, session_id, client=client, delegation=None
        )

    return {"error": f"Unknown tool '{name}'"}


async def chat_turn(
    client: Any,
    db: Session,
    who: Principal,
    history: list[dict],
    user_message: str,
    period: str,
    session_id: int | None = None,
    system_override: str | list[dict[str, Any]] | None = None,
    tools_override: list[str] | list[dict[str, Any]] | None = None,
    model_override: str | None = None,
    memory_block: str | None = None,
    max_rounds: int | None = None,
    *,
    delegation: dict | None = None,
) -> AsyncIterator[dict]:
    """Yields {'type': 'chunk'|'tool', ...} events for the SSE chat endpoint.

    ``system_override`` / ``tools_override`` / ``model_override`` support the
    workflow planner and headless asset runners. ``tools_override=[]`` means
    no tools. ``delegation`` is accepted for caller compatibility.
    """
    del delegation  # accepted for API compatibility; channel delegation not ported yet
    episodic = memory_block or ""
    stage = _company_stage()
    messages = history[-HISTORY_TURNS * 2 :] + [
        {
            "role": "user",
            "content": (f"{episodic}\n" if episodic else "")
            + f"<context>Default period: {period}</context>\n{user_message}",
        }
    ]
    system = _executive_system(system_override)
    tools = _tool_defs(tools_override)
    model = _effective_model(model_override)

    for _ in range(max_rounds or MAX_TOOL_ROUNDS):
        stream_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            stream_kwargs["tools"] = tools
        async with client.messages.stream(**stream_kwargs) as stream:
            async for text in stream.text_stream:
                yield {"type": "chunk", "content": text}
            final = await stream.get_final_message()
        if final.stop_reason != "tool_use":
            return
        # Preserve server_tool_use / web_search_tool_result blocks for next round.
        messages.append(
            {"role": "assistant", "content": [b.model_dump() for b in final.content]}
        )
        results = []
        tool_blocks = [b for b in final.content if getattr(b, "type", None) == "tool_use"]
        consults = [b for b in tool_blocks if b.name == "consult_specialist"]
        others = [b for b in tool_blocks if b.name != "consult_specialist"]
        consult_map: dict[str, Any] = {}
        if consults:
            parallel = await route_parallel(
                [dict(b.input) for b in consults],
                company_stage=stage,
                episodic_context=episodic,
            )
            for block, out in zip(consults, parallel, strict=False):
                consult_map[block.id] = out
                yield {
                    "type": "tool",
                    "name": block.name,
                    "specialist": block.input.get("specialist"),
                }
                audit(db, who, "copilot_tool", block.name, {"input": dict(block.input)})
        for block in others:
            out = await _dispatch_tool(
                db,
                who,
                block.name,
                dict(block.input),
                session_id,
                client,
                episodic_context=episodic,
                company_stage=stage,
            )
            tool_ev: dict[str, Any] = {"type": "tool", "name": block.name}
            if isinstance(out, dict) and out.get("artifact"):
                tool_ev["artifact"] = out["artifact"]
                yield {"type": "artifact", "artifact": out["artifact"], "tool": block.name}
            yield tool_ev
            audit(db, who, "copilot_tool", block.name, {"input": dict(block.input)})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, default=str),
                }
            )
        for block in consults:
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(consult_map[block.id], default=str),
                }
            )
        by_id = {r["tool_use_id"]: r for r in results}
        ordered = [by_id[b.id] for b in tool_blocks if b.id in by_id]
        messages.append({"role": "user", "content": ordered})
    yield {"type": "chunk", "content": "\n\n(Stopped: too many tool steps.)"}
