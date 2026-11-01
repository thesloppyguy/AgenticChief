"""Shared role/eval types and the workflow asset model registry."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "editor", "viewer"]
ALL_ROLES: list[str] = ["admin", "editor", "viewer"]


class EvalCase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    inputs: dict = Field(default_factory=dict)
    must_call: list[str] = Field(default_factory=list)
    must_mention: list[str] = Field(default_factory=list)


def _workflow_spec():
    from app.workflows.spec import WorkflowSpec

    return WorkflowSpec


class _Models(dict):
    def __missing__(self, kind: str):
        if kind == "workflow":
            self["workflow"] = _workflow_spec()
            return self["workflow"]
        raise KeyError(kind)


MODELS = _Models()
