"""Skill and agent definitions. Strictly validated: a definition is configuration that steers the model."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "editor", "viewer"]
ALL_ROLES: list[str] = ["admin", "editor", "viewer"]


class EvalCase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    inputs: dict = Field(default_factory=dict)  # skills: the input values; agents: {"message": "..."}
    must_call: list[str] = Field(default_factory=list)  # tools the run must use
    must_mention: list[str] = Field(default_factory=list)  # phrases the answer must contain


class SkillDef(BaseModel):
    instructions: str = Field(min_length=20, max_length=6000)
    inputs: dict = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    tools: list[str] = Field(default_factory=list, max_length=20)
    output_format: Literal["markdown", "json"] = "markdown"
    permissions: list[Role] = Field(default_factory=lambda: list(ALL_ROLES), min_length=1)
    eval_cases: list[EvalCase] = Field(default_factory=list, max_length=20)


class AgentDef(BaseModel):
    instructions: str = Field(min_length=20, max_length=6000)
    tools: list[str] = Field(default_factory=list, max_length=20)
    model: Literal["default", "deep", "fast"] = "default"
    permissions: list[Role] = Field(default_factory=lambda: list(ALL_ROLES), min_length=1)
    eval_cases: list[EvalCase] = Field(default_factory=list, max_length=20)
    # A supervisor may hand work to the specialists it names, and only those. The roster is a declared,
    # reviewable graph rather than a runtime depth counter: because a roster entry may not itself be a
    # supervisor (checked in service.validate), the graph is one level deep and cannot contain a cycle.
    supervisor: bool = False
    delegates_to: list[str] = Field(default_factory=list, max_length=8)


def _workflow_spec():
    """Imported late: app.workflows.spec imports this module for EvalCase and Role."""
    from app.workflows.spec import WorkflowSpec

    return WorkflowSpec


class _Models(dict):
    """`asset` carries three kinds. "workflow" resolves lazily to break the import cycle, but behaves
    like an ordinary entry everywhere else (approvals, the API, service.validate)."""

    def __missing__(self, kind: str):
        if kind == "workflow":
            self["workflow"] = _workflow_spec()
            return self["workflow"]
        raise KeyError(kind)


MODELS = _Models({"skill": SkillDef, "agent": AgentDef})
