"""Skills and agents: create, version, validate, evaluate, resolve for a run. Publication is approved
by a second admin (see approvals.actions.publish_asset)."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.logger import audit
from app.core.config import settings
from app.core.security import Principal, Role
from app.db.models import Asset, AssetVersion

from .definitions import MODELS, AgentDef, SkillDef

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
FLAT_TYPES = {"string", "number", "integer", "boolean"}


def tool_names() -> set[str]:
    """The Copilot's built-in tools. Imported on use: copilot.tools reaches the approvals package, which
    imports this module."""
    from app.copilot.tools import TOOLS

    return {t["name"] for t in TOOLS}


MODEL_FOR = {"default": lambda: settings.default_model, "deep": lambda: settings.deep_reasoning_model,
             "fast": lambda: settings.routing_model}


class AssetError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _now() -> datetime:
    return datetime.now(UTC)


def lifecycle_of(a: Asset) -> str:
    if a.deprecated:
        return "deprecated"
    if a.published_version is not None:
        return "published" if a.published_version == a.version else "update_pending"
    return "validated" if a.validated_version == a.version else "draft"


def parse_definition(kind: str, raw: dict):
    try:
        return MODELS[kind](**raw)
    except ValidationError as e:
        first = e.errors()[0]
        raise AssetError(422, f"{'.'.join(map(str, first['loc'])) or 'definition'}: {first['msg']}") from e


def create(db: Session, who: Principal, kind: str, key: str, name: str, description: str, raw: dict,
           builtin: bool = False) -> Asset:
    if not KEY_RE.match(key):
        raise AssetError(422, "key must be lowercase letters, digits and underscores, starting with a letter")
    if db.scalar(select(Asset.id).where(Asset.kind == kind, Asset.key == key)):
        raise AssetError(409, f"a {kind} with the key '{key}' already exists")
    definition = parse_definition(kind, raw).model_dump()
    a = Asset(kind=kind, key=key, name=name.strip()[:120], description=description.strip()[:500], version=1,
              builtin=builtin, lifecycle="draft", created_by=who.user_id)
    db.add(a)
    db.flush()
    db.add(AssetVersion(asset_id=a.id, version=1, definition=definition, created_by=who.user_id))
    audit(db, who, f"{kind}_created", key)
    db.commit()
    return a


def new_version(db: Session, who: Principal, a: Asset, raw: dict) -> Asset:
    if a.builtin:
        raise AssetError(403, "Built-in assets cannot be edited. Create your own copy under a new key.")
    definition = parse_definition(a.kind, raw).model_dump()
    if definition == latest(db, a).definition:
        raise AssetError(422, "That is identical to the current version")
    a.version += 1
    a.updated_at = _now()
    db.add(AssetVersion(asset_id=a.id, version=a.version, definition=definition, created_by=who.user_id))
    a.lifecycle = lifecycle_of(a)
    audit(db, who, f"{a.kind}_version", f"{a.key} v{a.version}")
    db.commit()
    return a


def version_row(db: Session, a: Asset, version: int) -> AssetVersion | None:
    return db.scalar(select(AssetVersion).where(AssetVersion.asset_id == a.id, AssetVersion.version == version))


def latest(db: Session, a: Asset) -> AssetVersion:
    return version_row(db, a, a.version)


def get(db: Session, kind: str, key: str) -> Asset:
    a = db.scalar(select(Asset).where(Asset.kind == kind, Asset.key == key))
    if a is None:
        raise AssetError(404, f"{kind} not found")
    return a


# --- validation ----------------------------------------------------------------------------

def workflow_checks(spec) -> list[dict]:
    """The pure half of a workflow's validation. What needs the database (are the skills, agents and
    capabilities it names actually published?) lives in reference_checks."""
    from app.approvals.actions import ACTIONS, Risk
    from app.workflows.spec import references

    out: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        out.append({"name": name, "ok": ok, "detail": detail})

    seen: set[str] = set()
    backwards, forwards = True, []
    for s in spec.steps:
        for ref in references(s.args):
            if ref not in seen:
                backwards, _ = False, forwards.append(f"{s.key} -> {ref}")
        seen.add(s.key)
    add("references_are_backwards", backwards,
        f"a step may only read earlier steps: {', '.join(forwards)}" if forwards else "")

    bare = {t for t in spec.tools if ":" not in t}
    # propose_action and delegate are never reachable as a plain tool step: proposing has its own
    # typed step (so a reviewer reads the action by name), and a workflow may not reach a sub-agent.
    forbidden = sorted(bare & {"delegate"})
    add("no_delegation_from_a_workflow", not forbidden,
        "a workflow cannot delegate to a sub-agent" if forbidden else "")
    unknown_tools = sorted(bare - tool_names() - {"propose_action"})
    add("workflow_tools_exist", not unknown_tools,
        f"unknown tools: {', '.join(unknown_tools)}" if unknown_tools else "")

    actions = [s.args.get("action") for s in spec.steps if s.type == "propose"]
    unknown_actions = sorted({a for a in actions if a not in ACTIONS})
    add("actions_exist", not unknown_actions,
        f"unknown actions: {', '.join(unknown_actions)}" if unknown_actions else "")
    destructive = sorted({a for a in actions if a in ACTIONS and ACTIONS[a].risk is Risk.DESTRUCTIVE})
    add("actions_are_not_destructive", not destructive,
        f"destructive actions are denied by policy: {', '.join(destructive)}" if destructive else "")

    keys = {s.key for s in spec.steps}
    missing = sorted({i for s in spec.steps if s.type == "summarize"
                      for i in s.args.get("inputs", []) if i not in keys})
    add("summarize_inputs_exist", not missing,
        f"no such step: {', '.join(missing)}" if missing else "")
    return out


def reference_checks(db: Session, spec) -> list[dict]:
    """Every skill or agent a workflow names must be published right now. Re-run at publication, so a
    workflow validated last month whose skill was since deprecated cannot go live."""
    out = []
    for ref in spec.tools:
        if ":" not in ref:
            continue
        kind, key = ref.split(":", 1)
        row = db.scalar(select(Asset).where(Asset.kind == kind, Asset.key == key))
        ok = row is not None and row.published_version is not None and not row.deprecated
        out.append({"name": f"uses:{ref}", "ok": ok,
                    "detail": "" if ok else f"no published {kind} with the key '{key}'"})
    return out


def static_checks(kind: str, d: SkillDef | AgentDef) -> list[dict]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # A workflow is checked on its own terms: its `tools` is a derived list of what the plan reaches,
    # and a plan of scorecard and summarize steps legitimately reaches no tool at all.
    if kind == "workflow":
        return workflow_checks(d)

    unknown = sorted(set(d.tools) - tool_names())
    add("tools_exist", not unknown, f"unknown tools: {', '.join(unknown)}" if unknown else "")
    add("has_tools", bool(d.tools), "" if d.tools else "with no tools it can only talk; give it the tools it needs")
    if "propose_action" in d.tools:
        add("action_proposals_are_gated", True, "can file requests, which still need a human's approval")
    if isinstance(d, AgentDef):
        # Delegation and the supervisor flag must agree, in both directions: the roster is what the
        # approver reviews, so it must never be possible to delegate without declaring to whom.
        add("delegate_requires_supervisor", "delegate" not in d.tools or d.supervisor,
            "" if "delegate" not in d.tools or d.supervisor
            else "it has the delegate tool but is not marked as a supervisor")
        add("a_supervisor_has_a_roster", not d.supervisor or (bool(d.delegates_to) and "delegate" in d.tools),
            "" if not d.supervisor or (d.delegates_to and "delegate" in d.tools)
            else "a supervisor needs the delegate tool and at least one specialist")
        add("a_roster_needs_the_supervisor_flag", not d.delegates_to or d.supervisor,
            "" if not d.delegates_to or d.supervisor else "it names specialists but is not a supervisor")
        dupes = len(d.delegates_to) != len(set(d.delegates_to))
        add("roster_has_no_duplicates", not dupes, "the same specialist is listed twice" if dupes else "")
    if isinstance(d, SkillDef):
        try:
            Draft202012Validator.check_schema(d.inputs)
            add("inputs_schema_is_valid", True)
        except SchemaError as e:
            add("inputs_schema_is_valid", False, e.message[:120])
            return checks
        props = d.inputs.get("properties", {})
        bad = sorted(k for k, v in props.items() if v.get("type") not in FLAT_TYPES)
        add("inputs_are_flat", not bad, f"inputs must be string, number, integer or boolean: {', '.join(bad)}" if bad else "")
        used = set(PLACEHOLDER.findall(d.instructions))
        missing = sorted(used - set(props))
        add("placeholders_match_inputs", not missing, f"instructions use {{{'}, {'.join(missing)}}} which is not an input" if missing else "")
        for case in d.eval_cases:
            errs = list(Draft202012Validator(d.inputs).iter_errors(case.inputs))
            add(f"eval_case_inputs:{case.name}", not errs, errs[0].message[:100] if errs else "")
    for case in d.eval_cases:
        unk = sorted(set(case.must_call) - tool_names())
        add(f"eval_case_tools:{case.name}", not unk, f"unknown tools: {', '.join(unk)}" if unk else "")
    return checks


def roster_checks(db: Session, d: SkillDef | AgentDef) -> list[dict]:
    """The part of a roster that needs the database. Kept out of static_checks so that stays pure.

    A specialist may not itself be a supervisor: that is what keeps the delegation graph one level
    deep and free of cycles, without a runtime depth count having to be correct.
    """
    if not isinstance(d, AgentDef) or not d.delegates_to:
        return []
    checks = []
    for key in d.delegates_to:
        target = db.scalar(select(Asset).where(Asset.kind == "agent", Asset.key == key))
        if target is None or target.published_version is None or target.deprecated:
            checks.append({"name": f"specialist:{key}", "ok": False,
                           "detail": "no published agent with that key"})
            continue
        row = version_row(db, target, target.published_version)
        nested = AgentDef(**row.definition)
        checks.append({"name": f"specialist:{key}", "ok": not nested.supervisor,
                       "detail": "a supervisor cannot be someone else's specialist" if nested.supervisor else ""})
    return checks


def validate(db: Session, who: Principal, a: Asset) -> dict:
    row = latest(db, a)
    d = MODELS[a.kind](**row.definition)
    checks = static_checks(a.kind, d) + roster_checks(db, d)
    if a.kind == "workflow":
        checks += reference_checks(db, d)
    ok = all(c["ok"] for c in checks)
    a.validation = {"checked_at": _now().isoformat(timespec="seconds"), "ok": ok, "version": a.version, "checks": checks}
    if ok:
        a.validated_version, row.validated = a.version, True
    a.lifecycle = lifecycle_of(a)
    audit(db, who, f"{a.kind}_validated", a.key, {"ok": ok, "version": a.version})
    db.commit()
    return a.validation


def deprecate(db: Session, who: Principal, a: Asset) -> Asset:
    if a.builtin:
        raise AssetError(403, "Built-in assets cannot be deprecated")
    a.deprecated = True
    a.lifecycle = lifecycle_of(a)
    audit(db, who, f"{a.kind}_deprecated", a.key)
    db.commit()
    return a


def publish_version(db: Session, approver: Principal, a: Asset, version: int) -> None:
    """Called only by the approval executor."""
    a.published_version = version
    a.lifecycle = lifecycle_of(a)
    audit(db, approver, f"{a.kind}_published", f"{a.key} v{version}")


# --- running -------------------------------------------------------------------------------

@dataclass
class RunSpec:
    label: str
    extra_system: str
    tool_names: list[str]
    model: str
    version: int
    supervisor: bool = False
    delegates_to: tuple[str, ...] = ()


def _fill(template: str, values: dict) -> str:
    """Substitute {name} placeholders. A plain regex swap (no str.format), so an input can never reach
    attributes or reinterpret braces."""
    return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


def _inputs(schema: dict, supplied: dict) -> dict:
    props = schema.get("properties", {})
    values = {k: v["default"] for k, v in props.items() if "default" in v}
    values.update(supplied)
    unknown = sorted(set(values) - set(props))
    if unknown:
        raise AssetError(422, f"unknown input(s): {', '.join(unknown)}")
    errs = sorted(Draft202012Validator(schema).iter_errors(values), key=lambda e: list(e.path))
    if errs:
        where = ".".join(map(str, errs[0].path)) or "inputs"
        raise AssetError(422, f"invalid {where}: {errs[0].message[:120]}")
    return values


def resolve(db: Session, who: Principal, kind: str, key: str, inputs: dict | None = None,
            allow_draft: bool = False) -> RunSpec:
    if kind == "workflow":  # a workflow is compiled and run, never turned into a prompt
        raise AssetError(422, "a workflow is run, not resolved")
    a = get(db, kind, key)
    admin = who.role is Role.ADMIN
    version = a.version if (allow_draft and admin) else a.published_version  # only admins may try a draft
    if version is None:
        # Non-admins must not learn that an unpublished asset exists.
        raise AssetError(409 if admin else 404, f"this {kind} is not published yet" if admin else f"{kind} not found")
    if a.deprecated:
        raise AssetError(409, f"this {kind} has been deprecated")
    row = version_row(db, a, version)
    d = MODELS[kind](**row.definition)
    if who.role.value not in d.permissions and not admin:
        raise AssetError(403, f"your role cannot use this {kind}")
    allowed = sorted(set(d.tools) & tool_names())
    if kind == "skill":
        values = _inputs(d.inputs, inputs or {})
        text = (f"You are running the skill \"{a.name}\". Follow these instructions.\n\n{_fill(d.instructions, values)}\n\n"
                f"Format the answer as {'a single JSON object' if d.output_format == 'json' else 'concise Markdown'}. "
                "Use only the tools you have been given; if the data you need is not available, say so.")
        return RunSpec(a.name, text, allowed, settings.default_model, version)
    text = f"You are acting as the specialist \"{a.name}\".\n\n{d.instructions}"
    if d.supervisor and d.delegates_to:
        text += "\n\nYour specialists: " + ", ".join(d.delegates_to) + \
                ". Delegate pillar work to them rather than deriving it yourself, and name which " \
                "specialist each finding came from."
    return RunSpec(a.name, text, allowed, MODEL_FOR[d.model](), version,
                   supervisor=d.supervisor, delegates_to=tuple(d.delegates_to))


# --- running headlessly ----------------------------------------------------------------------

async def run_headless(client, db: Session, who: Principal, spec: RunSpec, message: str, period: str,
                       *, delegation: dict | None = None, max_rounds: int | None = None) -> tuple[str, set[str]]:
    """One self-contained run of a skill or agent: no session, no history, nothing persisted.

    Shared by evals and by delegation, so a sub-agent runs through exactly the path its evals proved.
    `who` is passed straight through, so a sub-agent can never see more than its caller.
    """
    from app.copilot.orchestrator import chat_turn

    text, called = [], set()
    async for ev in chat_turn(client, db, who, [], message, period, None, spec.extra_system, spec.tool_names,
                              spec.model, delegation=delegation, max_rounds=max_rounds):
        if ev["type"] == "chunk":
            text.append(ev["content"])
        elif ev["type"] == "tool":
            called.add(ev["name"])
    return "".join(text), called


# --- evals ---------------------------------------------------------------------------------


def run_evals(db: Session, who: Principal, a: Asset, client, period: str) -> dict:
    """Run the eval cases of the latest version against the model. Needs a live client."""
    row = latest(db, a)
    d = MODELS[a.kind](**row.definition)
    if not d.eval_cases:
        raise AssetError(422, "this version has no eval cases")
    results = []
    for case in d.eval_cases:
        try:
            if a.kind == "skill":
                values = _inputs(d.inputs, case.inputs)
                spec = RunSpec(a.name, f"Skill \"{a.name}\".\n\n{_fill(d.instructions, values)}", sorted(set(d.tools) & tool_names()),
                               settings.default_model, a.version)
                message = f"Run the \"{a.name}\" skill."
            else:
                spec = RunSpec(a.name, d.instructions, sorted(set(d.tools) & tool_names()), MODEL_FOR[d.model](), a.version)
                message = str(case.inputs.get("message", ""))
            text, called = asyncio.run(run_headless(client, db, who, spec, message, period))
        except AssetError as e:
            results.append({"case": case.name, "passed": False, "problems": [e.message]})
            continue
        except Exception as e:  # noqa: BLE001 - one failing case must not hide the others
            results.append({"case": case.name, "passed": False, "problems": [f"run failed ({type(e).__name__})"]})
            continue
        problems = [f"did not call {t}" for t in case.must_call if t not in called]
        problems += [f"answer does not mention '{m}'" for m in case.must_mention if m.lower() not in text.lower()]
        results.append({"case": case.name, "passed": not problems, "problems": problems})
    passed = all(r["passed"] for r in results)
    row.eval_passed = passed
    row.eval_results = {"ran_at": _now().isoformat(timespec="seconds"), "version": a.version, "cases": results}
    audit(db, who, f"{a.kind}_evaluated", a.key, {"passed": passed, "cases": len(results)})
    db.commit()
    return row.eval_results
