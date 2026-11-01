"""Agent Council API (OpenExecutive port)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.executive_proxy import ExecutiveProxy
from app.agents.overrides import (
    EXECUTIVE_AGENT_ID,
    append_instructions,
    clear_override,
    get_override,
    list_history,
    rollback_to,
    set_override,
)
from app.agents.presets import (
    PRESET_IDS,
    PRESETS,
    AgentState,
    PresetId,
    preset_available,
    preset_status,
    writes_for,
)
from app.core.security import Principal, get_principal, require_admin
from app.orchestrator.router import SPECIALIST_DESCRIPTIONS, SPECIALIST_REGISTRY
from app.providers import allowed_models_for, model_options_for

router = APIRouter(prefix="/agents", tags=["agents"])

INSTRUCTIONS_MAX_CHARS = 4000
_executive = ExecutiveProxy()


def _registry() -> dict[str, Any]:
    return {EXECUTIVE_AGENT_ID: _executive, **SPECIALIST_REGISTRY}


def _role_default(name: str) -> str:
    if name == EXECUTIVE_AGENT_ID:
        return "Executive"
    description = SPECIALIST_DESCRIPTIONS.get(name, name)
    return description.split(" — ")[0] if " — " in description else description


class AgentMeta(BaseModel):
    name: str
    role: str
    model: str
    deep_reasoning: bool
    domains: list[str]
    has_override: bool = False
    visibility: str = "internal"


class AgentDetail(BaseModel):
    name: str
    role: str
    role_default: str
    model: str
    model_default: str
    deep_reasoning: bool
    deep_reasoning_default: bool
    prompt: str
    prompt_default: str
    domains: list[str]
    has_override: bool
    overridden_fields: list[str]
    updated_at: str | None = None
    instructions: str | None = None


class AgentPatch(BaseModel):
    prompt: str | None = None
    model: str | None = None
    use_deep_reasoning: bool | None = None
    role: str | None = None
    instructions: str | None = Field(None, max_length=INSTRUCTIONS_MAX_CHARS)


class AgentTestRequest(BaseModel):
    query: str
    prompt: str | None = None
    instructions: str | None = Field(None, max_length=INSTRUCTIONS_MAX_CHARS)
    model: str | None = None
    use_deep_reasoning: bool | None = None


class PresetApply(BaseModel):
    preset: PresetId


@router.get("")
def list_agents(_who: Principal = Depends(get_principal)) -> list[AgentMeta]:
    out: list[AgentMeta] = []
    for name, agent in _registry().items():
        ov = get_override(name)
        out.append(
            AgentMeta(
                name=name,
                role=(ov.role if ov and ov.role else _role_default(name)),
                model=agent.effective_model(),
                deep_reasoning=agent.effective_use_deep_reasoning(),
                domains=[agent.domain],
                has_override=ov is not None,
                visibility=getattr(agent, "visibility", "internal"),
            )
        )
    return out


@router.get("/models")
def model_options(_who: Principal = Depends(require_admin)) -> list[dict[str, str]]:
    return model_options_for()


def settings_default_for(agent: Any) -> str:
    from app.config import get_settings

    s = get_settings()
    # Match specialist class property defaults
    if getattr(agent, "use_deep_reasoning", False) and agent.name in {
        "cso",
        "cfo",
        "gc",
        "board_comms",
    }:
        return s.deep_reasoning_model
    if agent.name == "triage":
        return s.routing_model
    return s.default_model


def _agent_states() -> list[AgentState]:
    return [
        AgentState(
            agent_id=name,
            model_default=settings_default_for(agent),
            deep_default=bool(agent.__class__.use_deep_reasoning),
            model_override=(get_override(name).model if get_override(name) else None),
            deep_override=(
                get_override(name).use_deep_reasoning if get_override(name) else None
            ),
            core=getattr(agent, "visibility", "internal") == "core",
        )
        for name, agent in _registry().items()
    ]


@router.get("/presets")
def list_presets(_who: Principal = Depends(require_admin)) -> dict[str, Any]:
    allowed = allowed_models_for()
    status = preset_status(_agent_states(), allowed=allowed)
    return {
        "presets": [
            {
                "id": p.id,
                "label": p.label,
                "description": p.description,
                "available": preset_available(p.id, allowed),
            }
            for p in PRESETS.values()
        ],
        "status": {
            "active": status.active,
            "base": status.base,
            "custom_agents": status.custom_agents,
        },
    }


@router.post("/presets/{preset_id}")
def apply_preset(preset_id: str, _who: Principal = Depends(require_admin)) -> dict[str, Any]:
    if preset_id not in PRESET_IDS:
        raise HTTPException(404, "Unknown preset")
    allowed = allowed_models_for()
    for write in writes_for(preset_id, _agent_states(), allowed=allowed):  # type: ignore[arg-type]
        if write.model is None and write.deep is None:
            clear_override(write.agent_id)
            continue
        set_override(
            write.agent_id,
            model=write.model,
            use_deep_reasoning=write.deep,
            model_set=True,
            deep_set=True,
        )
    return list_presets(_who)


@router.get("/{name}")
def get_agent(name: str, _who: Principal = Depends(require_admin)) -> AgentDetail:
    agent = _registry().get(name)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    ov = get_override(name)
    default_model = settings_default_for(agent)
    default_deep = bool(agent.__class__.use_deep_reasoning)
    default_prompt = agent.get_system_prompt()
    overridden: list[str] = []
    if ov:
        if ov.prompt is not None:
            overridden.append("prompt")
        if ov.model is not None:
            overridden.append("model")
        if ov.use_deep_reasoning is not None:
            overridden.append("use_deep_reasoning")
        if ov.role is not None:
            overridden.append("role")
        if ov.instructions is not None:
            overridden.append("instructions")
    return AgentDetail(
        name=name,
        role=(ov.role if ov and ov.role else _role_default(name)),
        role_default=_role_default(name),
        model=agent.effective_model(),
        model_default=default_model,
        deep_reasoning=agent.effective_use_deep_reasoning(),
        deep_reasoning_default=default_deep,
        prompt=agent.base_system_prompt(),
        prompt_default=default_prompt,
        domains=[agent.domain],
        has_override=ov is not None,
        overridden_fields=overridden,
        updated_at=ov.updated_at if ov else None,
        instructions=ov.instructions if ov else None,
    )


@router.patch("/{name}")
def patch_agent(
    name: str, body: AgentPatch, _who: Principal = Depends(require_admin)
) -> AgentDetail:
    if name not in _registry():
        raise HTTPException(404, "Agent not found")
    fields = body.model_dump(exclude_unset=True)
    set_override(
        name,
        prompt=fields.get("prompt"),
        model=fields.get("model"),
        use_deep_reasoning=fields.get("use_deep_reasoning"),
        role=fields.get("role"),
        instructions=fields.get("instructions"),
        prompt_set="prompt" in fields,
        model_set="model" in fields,
        deep_set="use_deep_reasoning" in fields,
        role_set="role" in fields,
        instructions_set="instructions" in fields,
    )
    return get_agent(name, _who)


@router.delete("/{name}")
def reset_agent(name: str, _who: Principal = Depends(require_admin)) -> dict[str, str]:
    if name not in _registry():
        raise HTTPException(404, "Agent not found")
    clear_override(name)
    return {"status": "reset"}


@router.get("/{name}/history")
def agent_history(name: str, _who: Principal = Depends(require_admin)) -> list[dict]:
    if name not in _registry():
        raise HTTPException(404, "Agent not found")
    return [h.model_dump() for h in list_history(name)]


@router.post("/{name}/rollback/{history_id}")
def agent_rollback(
    name: str, history_id: int, _who: Principal = Depends(require_admin)
) -> AgentDetail:
    if name not in _registry():
        raise HTTPException(404, "Agent not found")
    result = rollback_to(history_id)
    if result is None or result.agent_id != name:
        raise HTTPException(404, "History entry not found")
    return get_agent(name, _who)


@router.post("/{name}/test")
async def test_agent(
    name: str, body: AgentTestRequest, _who: Principal = Depends(require_admin)
) -> dict[str, str]:
    agent = _registry().get(name)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    prompt = body.prompt if body.prompt is not None else agent.base_system_prompt()
    prompt = append_instructions(prompt, body.instructions)
    text = await agent.analyze(
        query=body.query,
        system_prompt_override=prompt,
        model_override=body.model,
        deep_reasoning_override=body.use_deep_reasoning,
        actor="agent_test",
    )
    return {"response": text}
