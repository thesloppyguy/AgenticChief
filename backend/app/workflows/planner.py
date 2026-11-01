"""Turn a plain-English description into a WorkflowSpec draft.

Goes through chat_turn with no tools, rather than client.messages.create, for one practical reason:
the test fakes implement messages.stream, so a planner on this path is testable headlessly with
ScriptedClient and never needs a real key.

The output is always a draft for a human to review. It is never persisted automatically, never
published automatically, and an invalid plan is never silently repaired into a different one.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.approvals.actions import ACTIONS
from app.assets.service import reference_checks, workflow_checks
from app.core.security import Principal
from app.kpi_registry.seed import PILLAR_WEIGHTS

from .spec import MAX_STEPS, WorkflowSpec

MAX_REPAIRS = 1  # one correction round, then hand the draft back for a human to fix

# Frozen: never interpolated, so it stays a stable cached prefix.
PLANNER_SYSTEM = """You plan workflows for a Group HR scorecard platform.

Output exactly ONE JSON object and nothing else. No prose, no explanation, no markdown around it.

Shape:
{"title": str, "steps": [{"key": str, "label": str, "type": str, "args": {...}}]}

`key` is lower_snake_case and unique. `label` is a short human sentence. There are SIX step types:

- "scorecard"  args: {"scope": "group" or a company code, "period": "run"|"previous"|"YYYY-MM"}
                Computes the scorecard. This is how you get real numbers.
- "tool"       args: {"name": <tool name>, "args": {...}}
                Calls one read-only Copilot tool.
- "skill"      args: {"key": <published skill key>, "inputs": {...}}
- "agent"      args: {"key": <published agent key>, "message": str}
- "summarize"  args: {"inputs": [<earlier step keys>], "instructions": str}
                Writes narrative over earlier steps. It may phrase the facts but cannot invent numbers.
- "propose"    args: {"action": <action key>, "args": {...}}
                Files a request for a human to approve. It NEVER executes anything.

Referring to earlier work: inside any string argument you may use {period}, {previous_period}, or
{steps.<earlier_step_key>.<dotted.path>}. A reference must point to a step that comes BEFORE it.

Rules you must follow:
- At most 12 steps. The list is linear: no branches, no conditions, no loops, no repetition.
- Use only the tools, skills, agents and actions listed in the catalogue you are given. Invent nothing.
- Get numbers from a "scorecard" or "tool" step. Never ask a "summarize" step to work them out.
- If the request needs something the catalogue cannot do, plan what you can and leave the rest out.
"""


def catalogue(db: Session) -> dict:
    """The dynamic inventory. Goes in the user turn, never the cached system block."""
    from app.copilot.tools import TOOLS
    from app.knowledge.skills_repo import list_skills
    from app.orchestrator.router import SPECIALIST_REGISTRY

    del db
    return {
        "tools": sorted(t["name"] for t in TOOLS if t["name"] not in ("propose_action", "delegate")),
        "skills": sorted(s.frontmatter.name for s in list_skills()),
        "agents": sorted(SPECIALIST_REGISTRY.keys()),
        "actions": {k: a.description for k, a in sorted(ACTIONS.items())},
        "pillars": sorted(PILLAR_WEIGHTS),
        "max_steps": MAX_STEPS,
    }


def _first_object(text: str) -> dict | None:
    """The first balanced {...}, tolerating ``` fences and stray commentary around it."""
    start = text.find("{")
    if start < 0:
        return None
    depth, in_string, escape = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def check(db: Session, obj: dict) -> tuple[WorkflowSpec | None, list[str]]:
    """Parse and validate a candidate plan. Returns (spec, problems); never raises."""
    try:
        spec = WorkflowSpec(**obj)
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc'])) or 'plan'}: {err['msg']}" for err in e.errors()[:8]]
    except (TypeError, AttributeError):
        return None, ["the plan is not an object with 'title' and 'steps'"]
    failed = [c for c in workflow_checks(spec) + reference_checks(db, spec) if not c["ok"]]
    if failed:
        return None, [f"{c['name']}: {c['detail']}" for c in failed]
    return spec, []


async def _ask(client: Any, db: Session, who: Principal, history: list[dict], message: str,
               period: str) -> str:
    from app.copilot.orchestrator import chat_turn

    out = []
    async for ev in chat_turn(client, db, who, history, message, period, None, PLANNER_SYSTEM,
                              [], None, max_rounds=1):  # no tools: it only has to write the plan
        if ev["type"] == "chunk":
            out.append(ev["content"])
    return "".join(out)


async def draft(client: Any, db: Session, who: Principal, description: str, period: str) -> dict:
    """{"spec": {...}, "problems": [...], "raw": str}. `spec` is None when it could not be made valid."""
    opening = (f"<catalogue>\n{json.dumps(catalogue(db), sort_keys=True)}\n</catalogue>\n"
               f"Plan a workflow for this request:\n{description.strip()[:4000]}")
    text = await _ask(client, db, who, [], opening, period)
    obj = _first_object(text)
    spec, problems = check(db, obj) if obj is not None else (None, ["no JSON object was returned"])

    history = [{"role": "user", "content": opening}, {"role": "assistant", "content": text}]
    for _ in range(MAX_REPAIRS):
        if spec is not None:
            break
        repair = ("That plan is not valid:\n- " + "\n- ".join(problems) +
                  "\nReturn the corrected JSON object, and nothing else.")
        text = await _ask(client, db, who, history, repair, period)
        obj = _first_object(text)
        spec, problems = check(db, obj) if obj is not None else (None, ["no JSON object was returned"])

    return {"spec": spec.model_dump() if spec else None, "problems": problems,
            "raw": None if spec else text[:4000]}


_WS = re.compile(r"\s+")


def suggest_key(title: str) -> str:
    """A workable asset key from a title, for the UI to pre-fill. Not authoritative: the user may edit."""
    slug = _WS.sub("_", title.strip().lower())
    slug = re.sub(r"[^a-z0-9_]", "", slug).strip("_")[:48]
    return slug if slug and slug[0].isalpha() else f"wf_{slug}"[:48]
