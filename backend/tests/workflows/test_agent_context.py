"""Agent workflow steps must receive prior scorecard/tool outputs as context."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.db.models import WorkflowRun
from app.fixtures.chro_workflows import CHRO_WORKFLOWS
from app.workflows.compiler import _agent, _collect_artifacts, _result_summary, compile_spec
from app.workflows.engine import StepCtx
from app.workflows.spec import AgentArgs, WorkflowSpec


def _ctx(state: dict, period: str = "2026-11") -> StepCtx:
    return StepCtx(
        MagicMock(),
        WorkflowRun(
            workflow="x",
            period=period,
            status="running",
            requested_by="a",
            role="admin",
            state=state,
        ),
        None,
        state,
    )


def test_agent_args_accept_inputs():
    a = AgentArgs(key="chro", message="Advise using the scorecard.", inputs=["card"])
    assert a.inputs == ["card"]
    assert AgentArgs(key="chro", message="hello").inputs == []


def test_agent_inputs_validation_rejects_unknown_steps():
    from app.assets.service import workflow_checks

    spec = WorkflowSpec(
        title="t",
        steps=[
            {
                "key": "s",
                "label": "Ask CHRO",
                "type": "agent",
                "args": {"key": "chro", "message": "Use the scorecard.", "inputs": ["nope"]},
            }
        ],
    )
    checks = {c["name"]: c for c in workflow_checks(spec)}
    assert checks["agent_inputs_exist"]["ok"] is False


def test_agent_receives_explicit_scorecard_inputs(monkeypatch):
    captured: dict = {}

    class FakeAgent:
        name = "chro"

        async def analyze(self, query, context="", **_kw):
            captured["query"] = query
            captured["context"] = context
            return "Retention 92 is on track."

    from app.orchestrator import router

    monkeypatch.setitem(router.SPECIALIST_REGISTRY, "chro", FakeAgent())

    state = {"card": {"period": "2026-11", "group": {"score": 85.9, "status": "amber"}}}
    out = _agent(_ctx(state), AgentArgs(key="chro", message="Advise on refresh", inputs=["card"]))
    assert out["ran"] == "agent:chro"
    assert "Retention 92" in out["text"]
    assert "Advise on refresh" in captured["query"]
    assert "85.9" in captured["context"] and "2026-11" in captured["context"]


def test_agent_without_inputs_auto_includes_prior_steps(monkeypatch):
    captured: dict = {}

    class FakeAgent:
        name = "chro"

        async def analyze(self, query, context="", **_kw):
            captured["context"] = context
            return "ok"

    from app.orchestrator import router

    monkeypatch.setitem(router.SPECIALIST_REGISTRY, "chro", FakeAgent())

    state = {"card": {"period": "2026-11", "group": {"score": 85.9}}}
    out = _agent(_ctx(state), AgentArgs(key="chro", message="Use scorecard in context"))
    assert out["text"] == "ok"
    assert '"card"' in captured["context"] and "85.9" in captured["context"]


def test_agent_context_strips_synthetic_and_meta_noise(monkeypatch):
    captured: dict = {}

    class FakeAgent:
        name = "chro"

        async def analyze(self, query, context="", **_kw):
            captured["context"] = context
            return "ok"

    from app.orchestrator import router

    monkeypatch.setitem(router.SPECIALIST_REGISTRY, "chro", FakeAgent())

    state = {
        "card": {
            "period": "2026-11",
            "synthetic_data": True,
            "freshness": {"overall": "stale"},
            "calc_version": "v9",
            "group": {"score": 85.9, "status": "amber"},
        }
    }
    _agent(_ctx(state), AgentArgs(key="chro", message="Brief me", inputs=["card"]))
    assert "85.9" in captured["context"]
    assert "synthetic_data" not in captured["context"]
    assert "freshness" not in captured["context"]
    assert "calc_version" not in captured["context"]


def test_collect_artifacts_lifts_scorecard_and_tool_charts():
    state = {
        "card": {
            "period": "2026-11",
            "group": {
                "score": 85.9,
                "status": "amber",
                "pillar_coverage": 1.0,
                "companies_in_scope": 5,
                "companies_with_data": 5,
                "pillars": [
                    {
                        "pillar": "retention",
                        "score": 92.0,
                        "status": "green",
                        "eligible_weight": 0.1,
                        "kpis": [],
                    }
                ],
            },
            "no_source_kpis": [],
        },
        "pulse": {
            "cells": [],
            "artifact": {
                "kind": "workforce_pulse",
                "title": "Pulse",
                "source": "workforce.pulse",
            },
        },
    }
    arts = _collect_artifacts(_ctx(state))
    kinds = {a["kind"] for a in arts}
    assert "scorecard_summary" in kinds
    assert "workforce_pulse" in kinds


def test_compile_finalize_includes_artifacts_summary_and_period():
    spec = WorkflowSpec(
        title="Morning",
        steps=[
            {"key": "card", "label": "Card", "type": "scorecard", "args": {"scope": "group"}},
            {
                "key": "chro",
                "label": "Priorities",
                "type": "agent",
                "args": {"key": "chro", "message": "Write three bullets."},
            },
        ],
    )
    wf = compile_spec("chro_morning_brief", spec)
    state = {
        "card": {
            "period": "2026-11",
            "group": {
                "score": 85.9,
                "status": "amber",
                "pillars": [],
                "companies_in_scope": 5,
                "companies_with_data": 5,
            },
        },
        "chro": {"text": "## Morning brief\n\n- Call LTMR today.", "ran": "agent:chro"},
    }
    result = wf.finalize(_ctx(state))
    assert result["workflow"] == "chro_morning_brief"
    assert result["period"] == "2026-11"
    assert result["summary"] == "Morning brief"
    assert any(a.get("kind") == "scorecard_summary" for a in result["artifacts"])
    assert "chro" in result["steps"]


def test_result_summary_prefers_summarize_over_agent():
    spec = WorkflowSpec(
        title="t",
        steps=[
            {
                "key": "chro",
                "label": "Long",
                "type": "agent",
                "args": {"key": "chro", "message": "long draft"},
            },
            {
                "key": "summary",
                "label": "Short",
                "type": "summarize",
                "args": {"inputs": ["chro"], "instructions": "Keep it short please."},
            },
        ],
    )
    state = {
        "chro": {"text": "Long specialist wall of text with many paragraphs."},
        "summary": {"text": "Decide on LTMR retention this week."},
    }
    assert _result_summary(_ctx(state), spec.steps) == "Decide on LTMR retention this week."


def test_weekly_workforce_brief_wires_tools_not_agent_tool_calls():
    weekly = next(w for w in CHRO_WORKFLOWS if w["key"] == "weekly_workforce_brief")
    steps = weekly["definition"]["steps"]
    types = {s["key"]: s["type"] for s in steps}
    assert types["pulse"] == "tool"
    assert types["skills"] == "tool"
    assert types["succession"] == "tool"
    assert types["drafts"] == "tool"
    assert types["chro"] == "agent"
    assert types["summary"] == "summarize"
    chro_msg = next(s for s in steps if s["key"] == "chro")["args"]["message"]
    assert "Call get_workforce_pulse" not in chro_msg
    assert "get_skills_gap" not in chro_msg
    assert "inputs" in next(s for s in steps if s["key"] == "chro")["args"]
    tool_names = {s["args"]["name"] for s in steps if s["type"] == "tool"}
    assert tool_names == {
        "get_workforce_pulse",
        "get_skills_gap",
        "get_succession_bench",
        "list_draft_actions",
    }


def test_morning_brief_includes_pulse_and_draft_tools():
    morning = next(w for w in CHRO_WORKFLOWS if w["key"] == "chro_morning_brief")
    tools = [s for s in morning["definition"]["steps"] if s["type"] == "tool"]
    assert {t["args"]["name"] for t in tools} == {"get_workforce_pulse", "list_draft_actions"}


def test_executive_summarize_uses_exec_brief_system(monkeypatch):
    from app.reports import commentary

    seen: dict = {}

    class Client:
        messages = property(lambda self: self)

        def create(self, **kw):
            seen["system"] = kw["system"]
            from types import SimpleNamespace as NS

            return NS(
                stop_reason="end_turn",
                content=[NS(type="text", text="Decide on LTMR. Score is 67.1.")],
            )

    out = commentary.summarize(
        Client(),
        {"card": {"group": {"score": 67.1}}},
        "Board brief",
        executive=True,
    )
    assert "C-suite" in seen["system"] or "CHRO" in seen["system"]
    assert "Infographics carry detail" in seen["system"] or "infographics" in seen["system"].lower()
    # Must NOT use the monthly-review rule that requires stating synthetic data.
    assert "say clearly if the data is synthetic" not in seen["system"].lower()
    assert out["method"] == "ai"
