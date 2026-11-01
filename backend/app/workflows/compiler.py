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
from app.reports import commentary
from app.services import scorecard as sc

from .engine import Step, StepCtx, WorkflowDef
from .spec import MODEL_STEPS, REF_RE, WorkflowSpec, WorkflowStepSpec

NO_LLM = {"skipped": "no_llm_configured", "text": ""}

# Meta / noise keys that make specialists narrate demo flags instead of decisions.
_AGENT_DROP_KEYS = frozenset({
    "synthetic_data", "freshness", "calc_version", "thresholds", "no_source_kpis",
    "definition_ref", "scope_applied", "note", "source_freshness", "mock_sources_enabled",
    "ai_configured", "as_of_month", "export_key", "schedule_key", "source",
})


class CompileError(ValueError):
    pass


def _slim_for_agent(value: Any, *, depth: int = 0) -> Any:
    """Drop meta fields and trim heavy KPI trees so agents cite scores, not fixtures."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k in _AGENT_DROP_KEYS or k == "artifact":
                continue
            if k == "kpis" and isinstance(v, list):
                # Keep scoreable KPI labels only — not full achievement trees.
                slim_kpis = []
                for item in v[:12]:
                    if not isinstance(item, dict):
                        continue
                    slim_kpis.append({
                        kk: item.get(kk)
                        for kk in ("key", "score", "status", "excluded_reason", "group_score")
                        if item.get(kk) is not None
                    })
                out[k] = slim_kpis
                continue
            slim = _slim_for_agent(v, depth=depth + 1)
            if slim is not None:
                out[k] = slim
        return out
    if isinstance(value, list):
        return [_slim_for_agent(v, depth=depth + 1) for v in value[:40]]
    return value


def _scorecard_artifact_from_step(step: dict) -> dict | None:
    """Build a scorecard_summary chart payload from a scorecard step output."""
    from app.copilot.tools import _scorecard_summary_artifact

    if not isinstance(step, dict) or step.get("error"):
        return None
    period = step.get("period") or ""
    group = step.get("group")
    if isinstance(group, dict) and (group.get("score") is not None or group.get("pillars")):
        src = {**group, "no_source_kpis": step.get("no_source_kpis") or []}
        return _scorecard_summary_artifact(str(period), src)
    if step.get("score") is not None or step.get("pillars"):
        # Company-scoped card: flatten into the same shape the artifact builder expects.
        src = {
            "score": step.get("score"),
            "status": step.get("status"),
            "pillars": step.get("pillars") or [],
            "pillar_coverage": step.get("pillar_coverage"),
            "companies_in_scope": 1,
            "companies_with_data": 1,
            "no_source_kpis": step.get("no_source_kpis") or [],
        }
        return _scorecard_summary_artifact(str(period), src)
    return None


def _collect_artifacts(ctx: StepCtx) -> list[dict]:
    """Lift chart payloads for WorkflowResultView Infographics."""
    artifacts: list[dict] = []
    seen: set[str] = set()

    def _add(art: dict | None) -> None:
        if not isinstance(art, dict) or not art.get("kind"):
            return
        key = f"{art.get('kind')}:{art.get('title') or ''}:{art.get('source') or ''}"
        if key in seen:
            return
        seen.add(key)
        artifacts.append(art)

    for step in ctx.state.values():
        if not isinstance(step, dict):
            continue
        if "group" in step or ("score" in step and "pillars" in step):
            _add(_scorecard_artifact_from_step(step))
        nested = step.get("artifact")
        if isinstance(nested, dict):
            _add(nested)
        elif isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    _add(item)
    return artifacts


def _result_summary(ctx: StepCtx, steps: tuple[WorkflowStepSpec, ...]) -> str | None:
    """Prefer the last summarize text; else the first agent brief (first line / short)."""
    summarize_text: str | None = None
    agent_text: str | None = None
    for s in steps:
        out = ctx.state.get(s.key)
        if not isinstance(out, dict):
            continue
        text = out.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if s.type == "summarize":
            summarize_text = text.strip()
        elif s.type == "agent" and agent_text is None:
            agent_text = text.strip()
    chosen = summarize_text or agent_text
    if not chosen:
        return None
    # At-a-glance: first non-empty line, capped.
    for line in chosen.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:280]
    return chosen[:280]


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


def _skill(ctx: StepCtx, a) -> dict:
    """Load a Markdown playbook and ask the Executive to follow it."""
    from app.knowledge.skills_repo import SkillNotFoundError, get_skill
    from app.orchestrator.executive import chat_turn

    client = ctx.deps.get("allm")
    if client is None:
        return {**NO_LLM, "ran": f"skill:{a.key}"}
    try:
        skill = get_skill(a.key)
    except SkillNotFoundError as e:
        return {"error": str(e), "ran": f"skill:{a.key}"}
    message = (
        f"Follow the playbook `{skill.frontmatter.name}`.\n\n{skill.body}\n\n"
        f"Inputs: {dict(a.inputs)}"
    )

    async def _run() -> str:
        parts: list[str] = []
        async for ev in chat_turn(
            client, ctx.db, ctx.who, [], message, ctx.run.period, None, None, max_rounds=4
        ):
            if ev.get("type") == "chunk":
                parts.append(ev.get("content") or "")
        return "".join(parts)

    text = asyncio.run(_run())
    return {"text": text, "ran": f"skill:{a.key}"}


def _agent(ctx: StepCtx, a) -> dict:
    """Consult a code-registered specialist by key.

    Prior step outputs (scorecard, tools, earlier agents) are passed as `context` so the
    specialist can cite real numbers. Explicit `inputs` selects which steps; when omitted,
    every earlier step is included — matching how workflow prompts say "use the scorecard
    in context" even for already-published defs that never declared inputs.
    """
    from app.orchestrator.router import SPECIALIST_REGISTRY

    agent = SPECIALIST_REGISTRY.get(a.key)
    if agent is None:
        return {"error": f"unknown specialist '{a.key}'", "ran": f"agent:{a.key}"}

    raw = {k: ctx.state.get(k) for k in a.inputs} if a.inputs else dict(ctx.state)
    facts = {k: _slim_for_agent(v) for k, v in raw.items()}
    context = json.dumps(facts, default=str) if facts else ""

    async def _run() -> str:
        return await agent.analyze(query=a.message, context=context)

    try:
        text = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "ran": f"agent:{a.key}"}
    return {"text": text, "ran": f"agent:{a.key}"}


def _summarize(ctx: StepCtx, a) -> dict:
    """Narrative over earlier steps for C-level briefs: phrase facts, never invent numbers."""
    facts = {k: _slim_for_agent(ctx.state.get(k)) for k in a.inputs}
    client = ctx.deps.get("llm")  # commentary uses the sync client
    if client is None:
        return {**NO_LLM, "facts": sorted(facts)}
    return commentary.summarize(client, facts, a.instructions, executive=True)


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
    step_tuple = tuple(Step(s.key, s.label, _runner(s)) for s in spec.steps)

    def finalize(ctx: StepCtx) -> dict:
        artifacts = _collect_artifacts(ctx)
        summary = _result_summary(ctx, spec.steps)
        out: dict[str, Any] = {
            "workflow": key,
            "title": spec.title,
            "period": ctx.run.period,
            "steps": {s.key: ctx.state.get(s.key) for s in spec.steps},
            "artifacts": artifacts,
            "skipped": sorted(
                s.key for s in spec.steps
                if s.type in MODEL_STEPS
                and isinstance(ctx.state.get(s.key), dict)
                and ctx.state[s.key].get("skipped")
            ),
        }
        if summary:
            out["summary"] = summary
        return out

    return WorkflowDef(f"def:{key}", spec.title, step_tuple, finalize)
