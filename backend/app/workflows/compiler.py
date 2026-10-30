"""Compile a stored WorkflowSpec into the WorkflowDef the engine already runs.

The engine is not modified. It takes `Step(key, label, run)` where `run` is any callable over a
StepCtx; this module supplies those callables from a closed dispatch table, in the same style as
ACTIONS, JOBS and MODELS elsewhere in the codebase.

Determinism and resume: every step's output is persisted before the next starts, and completed steps
are skipped on resume, so a model-backed step runs exactly once. The spec language forbids a step from
reading anything outside `ctx.state`, which is what makes that safe.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.alerts.engine import prev_period
from app.approvals import service as approvals
from app.assets import service as asset_service
from app.reports import commentary
from app.services import scorecard as sc

from .engine import Step, StepCtx, WorkflowDef
from .spec import MODEL_STEPS, REF_RE, WorkflowSpec, WorkflowStepSpec

NO_LLM = {"skipped": "no_llm_configured", "text": ""}


class CompileError(ValueError):
    pass


# --- templating ---------------------------------------------------------------------------------

def _lookup(path: str, ctx: StepCtx) -> Any:
    if path == "period":
        return ctx.run.period
    if path == "previous_period":
        return prev_period(ctx.run.period)
    _, step_key, *rest = path.split(".")
    if step_key not in ctx.state:
        raise CompileError(f"step '{step_key}' has not run")  # forward refs are rejected at validation
    value: Any = ctx.state[step_key]
    for part in rest:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        else:
            return None
    return value


def resolve(value: Any, ctx: StepCtx) -> Any:
    """Substitute references. A whole-string reference yields the raw value (dict, list, number);
    anything else interpolates into text.

    Regex substitution, never str.format: a value must never be able to reach attributes or
    reinterpret braces (the same reasoning as assets.service._fill).
    """
    if isinstance(value, str):
        whole = REF_RE.fullmatch(value)
        if whole:
            return _lookup(whole.group(1), ctx)
        return REF_RE.sub(lambda m: _to_text(_lookup(m.group(1), ctx)), value)
    if isinstance(value, dict):
        return {k: resolve(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, ctx) for v in value]
    return value


def _to_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _period(ctx: StepCtx, which: str) -> str:
    if which == "run":
        return ctx.run.period
    return prev_period(ctx.run.period) or ctx.run.period if which == "previous" else which


# --- handlers -----------------------------------------------------------------------------------

def _scorecard(ctx: StepCtx, a) -> dict:
    period = _period(ctx, a.period)
    if a.scope == "group":
        return sc.build_scorecard(ctx.db, ctx.who, period)
    match = next((c for c in sc.visible_companies(ctx.db, ctx.who) if c.code == a.scope.upper()), None)
    if match is None:
        return {"error": "unknown company or no access", "scope": a.scope}
    return sc.build_company_scorecard(ctx.db, ctx.who, match.id, period)


def _tool(ctx: StepCtx, a) -> dict:
    from app.copilot.tools import run_tool

    # No client and no delegation budget: a workflow step can never reach a sub-agent this way.
    return run_tool(ctx.db, ctx.who, a.name, dict(a.args), None)


def _asset(ctx: StepCtx, kind: str, key: str, message: str, inputs: dict | None) -> dict:
    client = ctx.deps.get("allm")
    if client is None:  # mirrors commentary.generate: no client is a skip, not a failure
        return {**NO_LLM, "ran": f"{kind}:{key}"}
    try:
        spec = asset_service.resolve(ctx.db, ctx.who, kind, key, inputs)
    except asset_service.AssetError as e:
        return {"error": e.message, "ran": f"{kind}:{key}"}
    text, called = asyncio.run(asset_service.run_headless(
        client, ctx.db, ctx.who, spec, message, ctx.run.period))
    return {"text": text, "tools_called": sorted(called), "version": spec.version, "ran": f"{kind}:{key}"}


def _skill(ctx: StepCtx, a) -> dict:
    return _asset(ctx, "skill", a.key, f'Run the "{a.key}" skill.', dict(a.inputs))


def _agent(ctx: StepCtx, a) -> dict:
    return _asset(ctx, "agent", a.key, a.message, None)


def _summarize(ctx: StepCtx, a) -> dict:
    """Narrative over earlier steps, held to the same rule as the monthly review's commentary: the
    model may phrase the facts but may not invent a number."""
    facts = {k: ctx.state.get(k) for k in a.inputs}
    client = ctx.deps.get("llm")  # commentary uses the sync client
    if client is None:
        return {**NO_LLM, "facts": sorted(facts)}
    return commentary.summarize(client, facts, a.instructions)


def _propose(ctx: StepCtx, a) -> dict:
    """Files an approval request. It cannot execute: submit() only auto-executes a READ-risk action,
    and none is registered. On a scheduled run the requester is "scheduler", so no admin can ever
    self-approve what the workflow proposed."""
    try:
        res = approvals.submit(ctx.db, ctx.who, a.action, dict(a.args), via="workflow",
                               context={"workflow_run_id": ctx.run.id})
    except approvals.ApprovalError as e:
        return {"error": e.message, "action": a.action}
    return {"approval_id": res.approval.id, "verdict": res.verdict, "status": res.approval.status,
            "action": a.action, "note": "Filed for approval. Not executed."}


HANDLERS: dict[str, Callable[[StepCtx, BaseModel], dict]] = {
    "scorecard": _scorecard, "tool": _tool, "skill": _skill,
    "agent": _agent, "summarize": _summarize, "propose": _propose,
}


# --- compilation --------------------------------------------------------------------------------

def _runner(s: WorkflowStepSpec) -> Callable[[StepCtx], dict]:
    def run(ctx: StepCtx) -> dict:
        return HANDLERS[s.type](ctx, s.parsed(resolve(s.args, ctx)))

    return run


def compile_spec(key: str, spec: WorkflowSpec) -> WorkflowDef:
    return WorkflowDef(
        f"def:{key}", spec.title,
        tuple(Step(s.key, s.label, _runner(s)) for s in spec.steps),
        lambda ctx: {"workflow": key, "title": spec.title,
                     "steps": {s.key: ctx.state.get(s.key) for s in spec.steps},
                     "skipped": sorted(s.key for s in spec.steps
                                       if s.type in MODEL_STEPS
                                       and isinstance(ctx.state.get(s.key), dict)
                                       and ctx.state[s.key].get("skipped"))},
    )
