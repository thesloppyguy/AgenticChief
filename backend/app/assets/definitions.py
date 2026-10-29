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


MODELS = {"skill": SkillDef, "agent": AgentDef}
