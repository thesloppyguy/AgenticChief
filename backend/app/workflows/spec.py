"""A workflow written as data rather than Python, so one can be authored from a prompt and reviewed
before it runs.

Deliberately small: six step types, a linear list, and a closed templating syntax. No expressions, no
branching, no loops, no user-supplied code. Branching is what makes both resume and human review hard,
and a plan a human cannot read in ten seconds is a plan nobody will actually check.

References point strictly backwards (`{steps.<earlier>.<path>}`). That gives dependency order for free
and is what keeps the engine's resume contract safe: a step only ever reads what is already persisted.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.assets.definitions import ALL_ROLES, EvalCase, Role

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")  # one letter is a fine step key
# {period} | {previous_period} | {steps.<key>.<dotted.path>}
REF_RE = re.compile(r"\{(period|previous_period|steps\.[a-z][a-z0-9_]*(?:\.[a-zA-Z0-9_]+)*)\}")
MAX_STEPS = 12
PERIOD_RE = r"^(run|previous|\d{4}-(0[1-9]|1[0-2]))$"


class ScorecardArgs(BaseModel):
    scope: str = "group"  # "group" or a company code
    period: str = Field(default="run", pattern=PERIOD_RE)


class ToolArgs(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class SkillArgs(BaseModel):
    key: str
    inputs: dict = Field(default_factory=dict)


class AgentArgs(BaseModel):
    key: str
    message: str = Field(min_length=1, max_length=2000)
    # Earlier step keys to inject as <conversation_context>. Empty = every prior step
    # (so a scorecard that already ran reaches the specialist without re-authoring).
    inputs: list[str] = Field(default_factory=list, max_length=MAX_STEPS)


class SummarizeArgs(BaseModel):
    inputs: list[str] = Field(min_length=1, max_length=MAX_STEPS)  # step keys to summarise
    instructions: str = Field(min_length=10, max_length=2000)


class ProposeArgs(BaseModel):
    action: str
    args: dict = Field(default_factory=dict)


ARG_MODELS: dict[str, type[BaseModel]] = {
    "scorecard": ScorecardArgs, "tool": ToolArgs, "skill": SkillArgs,
    "agent": AgentArgs, "summarize": SummarizeArgs, "propose": ProposeArgs,
}
StepType = Literal["scorecard", "tool", "skill", "agent", "summarize", "propose"]
# Steps that need a model, and so are skipped when none is configured.
MODEL_STEPS = ("skill", "agent", "summarize")


class WorkflowStepSpec(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=80)
    type: StepType
    args: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> WorkflowStepSpec:
        if not KEY_RE.match(self.key):
            raise ValueError(f"step key '{self.key}' must be lower_snake_case")
        ARG_MODELS[self.type](**_blank_refs(self.args))  # shape must be right even before substitution
        return self

    def parsed(self, resolved: dict) -> BaseModel:
        return ARG_MODELS[self.type](**resolved)


def _blank_refs(value: Any) -> Any:
    """A copy with every {...} reference replaced by a placeholder of its own type, so an arg model can
    be validated at author time, before any step has produced a value."""
    if isinstance(value, str):
        return REF_RE.sub("x", value)
    if isinstance(value, dict):
        return {k: _blank_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank_refs(v) for v in value]
    return value


def references(value: Any) -> list[str]:
    """Every `steps.<key>` named anywhere inside an argument value."""
    if isinstance(value, str):
        return [m.split(".")[1] for m in REF_RE.findall(value) if m.startswith("steps.")]
    if isinstance(value, dict):
        return [r for v in value.values() for r in references(v)]
    if isinstance(value, list):
        return [r for v in value for r in references(v)]
    return []


class WorkflowSpec(BaseModel):
    """Shaped to satisfy the asset machinery: `tools`, `instructions`, `permissions` and `eval_cases`
    are what approvals.actions._precheck_publish_asset shows an approver."""

    title: str = Field(min_length=1, max_length=120)
    steps: list[WorkflowStepSpec] = Field(min_length=1, max_length=MAX_STEPS)
    permissions: list[Role] = Field(default_factory=lambda: list(ALL_ROLES), min_length=1)
    eval_cases: list[EvalCase] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _check(self) -> WorkflowSpec:
        keys = [s.key for s in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("step keys must be unique")
        return self

    @property
    def tools(self) -> list[str]:
        """Everything this plan can reach. The approver reads this to see what it may touch."""
        out: set[str] = set()
        for s in self.steps:
            if s.type == "tool":
                out.add(str(s.args.get("name", "")))
            elif s.type in ("skill", "agent"):
                out.add(f"{s.type}:{s.args.get('key', '')}")
            elif s.type == "propose":
                out.add("propose_action")
        return sorted(out)

    @property
    def instructions(self) -> str:
        """The plan as prose. _precheck_publish_asset shows the first 600 characters of this to the
        approver, so it has to be the thing they actually need to read."""
        lines = [f"{i}. {s.label} [{s.type}]" for i, s in enumerate(self.steps, 1)]
        return f"{self.title}\n" + "\n".join(lines)
