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
from app.org.companies import LNT_COMPANIES

from .spec import MAX_STEPS, WorkflowSpec

MAX_REPAIRS = 1  # one correction round, then hand the draft back for a human to fix

# Frozen: never interpolated, so it stays a stable cached prefix.
PLANNER_SYSTEM = """You plan workflows for a Group HR scorecard platform.

Output exactly ONE JSON object and nothing else. No prose, no explanation, no markdown around it.

Shape:
{"title": str, "steps": [{"key": str, "label": str, "type": str, "args": {...}}]}

`key` is lower_snake_case and unique. `label` is a short human sentence. There are SIX step types:

- "scorecard"  args: {"scope": "group" or a company code, "period": "run"|"previous"|"YYYY-MM"}
                Computes the scorecard. This is how you get real scorecard KPI numbers.
- "tool"       args: {"name": <tool name>, "args": {...}}
                Calls one read-only Copilot tool.
- "skill"      args: {"key": <published skill key>, "inputs": {...}}
- "agent"      args: {"key": <published agent key>, "message": str,
                       "inputs": [<earlier step keys>] (optional)}
                Consults a specialist. Pass scorecard/tool step keys in `inputs` whenever the
                message asks them to use numbers; omit `inputs` to auto-include every prior step.
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
- Scope: if the request names one Independent Company (IC), resolve it via the catalogue aliases
  (e.g. "LNT Mindtree" / "LTIMindtree" → LTIM) and pass that company_code. Never use scope "group"
  when the ask is about one IC.
- Period: use "run" (the scheduled/run period) unless the request names a month; put period into tool
  args that accept it so freshness can be checked.
- Domain honesty — never substitute proxies:
  * Succession / bench strength / critical-role coverage needs get_succession_coverage (or
    get_succession_bench). Talent Management scorecard KPIs (Top Talent Review, IDPs, PLI) measure
    whether talent processes ran — they are NOT succession data. Do not plan a scorecard or
    "explain the talent management pillar" step as a stand-in for a succession report.
  * If the catalogue cannot supply a required input, say so in the title (e.g. append
    " — data gap") and either omit that part or add a summarize step whose instructions list
    exactly which inputs are missing. Do not invent alternate steps that look complete.
- A useful succession plan is typically: resolve IC + period → get_succession_coverage → optional
  talent-pillar scorecard for context only (labelled as process compliance, not succession) →
  search_documents for succession material with citations → skill succession-ic-report or summarize
  into the report template → propose delivery/approval if the request asks to send or schedule.
- Prefer short, decisive titles: prefer "LTIM succession report" over long parenthetical hedges.
  Honesty about gaps belongs in a step label or summarize instructions, not a truncated title.
"""


def catalogue(db: Session) -> dict:
    """The dynamic inventory. Goes in the user turn, never the cached system block."""
    from app.copilot.tools import TOOLS
    from app.knowledge.skills_repo import list_skills
    from app.orchestrator.router import SPECIALIST_REGISTRY
    from app.workforce.loader import succession as succession_fixture

    del db
    succ = succession_fixture()
    by_ic = succ.get("by_ic") or {}
    companies = []
    for code, name, _ in LNT_COMPANIES:
        aliases = list((by_ic.get(code) or {}).get("aliases") or [])
        if name not in aliases:
            aliases = [name, *aliases]
        companies.append({"code": code, "name": name, "aliases": aliases})

    return {
        "tools": sorted(t["name"] for t in TOOLS if t["name"] not in ("propose_action", "delegate")),
        "skills": sorted(s.frontmatter.name for s in list_skills()),
        "agents": sorted(SPECIALIST_REGISTRY.keys()),
        "actions": {k: a.description for k, a in sorted(ACTIONS.items())},
        "pillars": sorted(PILLAR_WEIGHTS),
        "companies": companies,
        "domain_notes": {
            "succession": (
                "Use get_succession_coverage(company_code, period). Returns critical roles, "
                "readiness, 9-box, flight risk. Not the talent_management pillar."
            ),
            "scorecard_talent_management": (
                "Top Talent Review / IDPs / PLI = process compliance only; never a succession proxy."
            ),
        },
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
    """{"spec": {...}, "problems": [...], "raw": str, "suggested_key": str|None}."""
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

    key = suggest_key(spec.title) if spec else None
    return {"spec": spec.model_dump() if spec else None, "problems": problems,
            "raw": None if spec else text[:4000], "suggested_key": key}


_WS = re.compile(r"\s+")
_PARENS = re.compile(r"\([^)]*\)")


def suggest_key(title: str) -> str:
    """A workable asset key from a title, for the UI to pre-fill. Not authoritative: the user may edit.

    Parenthetical hedges (e.g. "partial: …") are stripped so keys stay short and readable.
    """
    cleaned = _PARENS.sub(" ", title)
    # Prefer IC codes when the title leads with one.
    for code, name, _ in LNT_COMPANIES:
        low = cleaned.lower()
        if low.startswith(code.lower()) or name.lower() in low[: max(24, len(name) + 4)]:
            cleaned = re.sub(re.escape(name), code, cleaned, count=1, flags=re.I)
            break
    slug = _WS.sub("_", cleaned.strip().lower())
    slug = re.sub(r"[^a-z0-9_]", "", slug).strip("_")
    slug = re.sub(r"_+", "_", slug)[:48].strip("_")
    return slug if slug and slug[0].isalpha() else f"wf_{slug}"[:48]
