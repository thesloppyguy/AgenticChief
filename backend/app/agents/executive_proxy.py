"""Council-facing proxy for the Executive orchestrator."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.config import get_settings


class ExecutiveProxy(BaseAgent):
    name = "executive"
    domain = "executive"
    visibility = "core"
    use_deep_reasoning = False

    @property
    def model(self) -> str:  # type: ignore[override]
        return get_settings().default_model

    def get_system_prompt(self) -> str:
        from app.prompts.executive_persona import EXECUTIVE_PERSONA_PROMPT

        # Voice persona placeholder is filled at runtime for chat; Council shows raw template.
        return EXECUTIVE_PERSONA_PROMPT.replace("{VOICE_PERSONA}", "Direct, calm, decisive.")
