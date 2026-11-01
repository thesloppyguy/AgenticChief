"""Stable Executive tools for listing and running saved scripts."""
from __future__ import annotations

import ast
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.orchestrator import saved_tools

Dispatch = Callable[[str, dict[str, Any]], Awaitable[Any]]

MAX_SCRIPT_CHARS = 20_000
MAX_CALLS = 40

SAVED_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "list_saved_tools",
        "description": "List enabled saved tools the Executive can run with run_script.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_script",
        "description": (
            "Run a saved tool by name, or execute an inline script and optionally save it. "
            "Scripts may be a JSON list of {tool, args} steps, or Python that sets `result` "
            "and may call call_tool(name, args)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "Saved tool name to run"},
                "script": {
                    "type": "string",
                    "description": "Inline script (JSON steps or Python)",
                },
                "inputs": {"type": "object", "description": "Inputs available as `inputs`"},
                "save_as": {
                    "type": "string",
                    "description": "If set with script, save successful script under this name",
                },
                "description": {
                    "type": "string",
                    "description": "Description when saving",
                },
            },
        },
    },
]


def _validate_python(source: str) -> None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.With, ast.AsyncWith)):
            raise ValueError("imports and with-statements are not allowed in scripts")
        if isinstance(node, ast.Attribute) and isinstance(node.attr, str):
            if node.attr.startswith("__"):
                raise ValueError("dunder attribute access is not allowed")


async def _run_json_steps(
    steps: list[dict[str, Any]], dispatch: Dispatch
) -> tuple[Any, int, list[str]]:
    results = []
    called: list[str] = []
    for step in steps[:MAX_CALLS]:
        name = str(step.get("tool") or "")
        args = dict(step.get("args") or {})
        if not name:
            continue
        called.append(name)
        results.append({"tool": name, "result": await dispatch(name, args)})
    return results, len(called), called


async def _run_python(
    source: str, inputs: dict[str, Any], dispatch: Dispatch
) -> tuple[Any, int, list[str]]:
    _validate_python(source)
    called: list[str] = []
    calls = {"n": 0}

    async def call_tool(name: str, args: dict[str, Any] | None = None) -> Any:
        if calls["n"] >= MAX_CALLS:
            raise RuntimeError("tool call budget exceeded")
        calls["n"] += 1
        called.append(name)
        return await dispatch(name, dict(args or {}))

    safe_builtins = {
        "True": True,
        "False": False,
        "None": None,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "list": list,
        "dict": dict,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "enumerate": enumerate,
        "range": range,
        "json": json,
        "print": lambda *a, **k: None,
    }
    # Always run inside an async function so `await call_tool(...)` works.
    wrapped = "async def __script_main():\n"
    for line in source.splitlines() or ["pass"]:
        wrapped += f"    {line}\n"
    wrapped += "    return result\n"
    loc: dict[str, Any] = {
        "inputs": inputs,
        "result": None,
        "call_tool": call_tool,
        "json": json,
    }
    exec(compile(wrapped, "<saved_tool>", "exec"), {"__builtins__": safe_builtins}, loc)
    out = await loc["__script_main"]()
    if out is not None:
        loc["result"] = out
    return loc.get("result"), calls["n"], called


async def handle(name: str, args: dict[str, Any], *, dispatch: Dispatch) -> Any:
    if name == "list_saved_tools":
        tools = [t for t in saved_tools.list_tools() if t.enabled]
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "kind": t.kind,
                    "version": t.active_version,
                }
                for t in tools
            ]
        }

    if name != "run_script":
        return {"error": f"unknown tool {name}"}

    tool_name = (args.get("tool") or "").strip()
    script = args.get("script")
    inputs = dict(args.get("inputs") or {})
    save_as = (args.get("save_as") or "").strip() or None
    description = (args.get("description") or "").strip() or "Saved tool"

    code = ""
    version = 0
    origin_name = tool_name or save_as or "inline"
    if tool_name:
        active = saved_tools.get_active_code(tool_name)
        if active is None:
            return {"error": f"saved tool '{tool_name}' not found"}
        if not active["enabled"]:
            return {"error": f"saved tool '{tool_name}' is disabled"}
        code = active["code"]
        version = int(active["version"])
    elif isinstance(script, str) and script.strip():
        code = script.strip()
        if len(code) > MAX_SCRIPT_CHARS:
            return {"error": "script too large"}
    else:
        return {"error": "provide tool= or script="}

    started = time.perf_counter()
    try:
        stripped = code.lstrip()
        if stripped.startswith("["):
            steps = json.loads(code)
            if not isinstance(steps, list):
                raise ValueError("JSON script must be a list of steps")
            result, call_count, called = await _run_json_steps(steps, dispatch)
        else:
            result, call_count, called = await _run_python(code, inputs, dispatch)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}

    duration_ms = int((time.perf_counter() - started) * 1000)
    text = json.dumps(result, default=str)[:8000]
    if tool_name and version:
        saved_tools.record_run(
            tool_name,
            version,
            result=text,
            call_count=call_count,
            duration_ms=duration_ms,
            origin="chat",
        )
    if save_as and isinstance(script, str):
        saved_tools.upsert_version(
            save_as,
            description=description,
            code=code,
            called_tools=called,
            origin="chat",
        )
    return {"result": result, "call_count": call_count, "duration_ms": duration_ms}
