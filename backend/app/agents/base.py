from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

from app.config import get_settings
from app.providers import get_provider, model_supports_deep_reasoning

_SPECIALIST_TIMEOUT = 180.0
logger = logging.getLogger(__name__)

AgentVisibility = Literal["core", "internal"]


class BaseAgent(ABC):
    name: str
    domain: str
    model: str
    use_deep_reasoning: bool = False
    visibility: AgentVisibility = "internal"

    @abstractmethod
    def get_system_prompt(self) -> str: ...

    def base_system_prompt(self) -> str:
        from app.agents.overrides import get_override

        ov = get_override(self.name)
        if ov is not None and ov.prompt is not None:
            return ov.prompt
        return self.get_system_prompt()

    def effective_system_prompt(self) -> str:
        from app.agents.overrides import append_instructions, get_override

        ov = get_override(self.name)
        return append_instructions(
            self.base_system_prompt(), ov.instructions if ov is not None else None
        )

    def effective_model(self) -> str:
        from app.agents.overrides import get_override

        ov = get_override(self.name)
        if ov is not None and ov.model is not None:
            return ov.model
        return self.model

    def effective_use_deep_reasoning(self) -> bool:
        from app.agents.overrides import get_override

        ov = get_override(self.name)
        if ov is not None and ov.use_deep_reasoning is not None:
            return ov.use_deep_reasoning
        return self.use_deep_reasoning

    async def analyze(
        self,
        query: str,
        context: str = "",
        retrieved_knowledge: str = "",
        episodic_context: str = "",
        failure_cases: str = "",
        department_memory: str = "",
        *,
        company_stage: str = "",
        principal_role: str = "",
        standing_facts: str = "",
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        deep_reasoning_override: bool | None = None,
        actor: str = "specialist",
    ) -> str:
        del actor  # usage logging is optional in this port
        system_prompt = (
            system_prompt_override
            if system_prompt_override is not None
            else self.effective_system_prompt()
        )
        model = model_override if model_override is not None else self.effective_model()
        use_deep = (
            deep_reasoning_override
            if deep_reasoning_override is not None
            else self.effective_use_deep_reasoning()
        )

        user_content = query
        if context:
            user_content = f"<conversation_context>\n{context}\n</conversation_context>\n\n{query}"
        if retrieved_knowledge:
            user_content = (
                f"<relevant_knowledge>\n{retrieved_knowledge}\n</relevant_knowledge>\n\n{user_content}"
            )
        if failure_cases:
            user_content = f"<failure_cases>\n{failure_cases}\n</failure_cases>\n\n{user_content}"
        if episodic_context:
            user_content = (
                f"<past_decisions>\n{episodic_context}\n</past_decisions>\n\n{user_content}"
            )
        if standing_facts:
            user_content = (
                f"<standing_facts>\n{standing_facts}\n</standing_facts>\n\n{user_content}"
            )
        if department_memory:
            user_content = (
                f"<department_memory>\n{department_memory}\n</department_memory>\n\n{user_content}"
            )
        role = principal_role.strip()
        if role:
            user_content = f"<principal_role>\n{role}\n</principal_role>\n\n{user_content}"
        stage = " ".join(company_stage.split())
        if stage:
            user_content = f"<company_stage>\n{stage}\n</company_stage>\n\n{user_content}"

        create_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "timeout": _SPECIALIST_TIMEOUT,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": user_content}],
        }
        if use_deep and model_supports_deep_reasoning(model):
            create_kwargs["thinking"] = {"type": "adaptive"}
            create_kwargs["output_config"] = {
                "effort": getattr(get_settings(), "specialist_effort", "low")
            }
            create_kwargs["max_tokens"] = 16000

        provider = get_provider(model)
        message = await provider.messages_create(**create_kwargs)
        text_blocks = [b for b in message.content if b.type == "text"]
        if not text_blocks:
            logger.warning(
                "specialist %s (%s) returned no text block (stop_reason=%s)",
                self.name,
                model,
                getattr(message, "stop_reason", None),
            )
        return text_blocks[0].text if text_blocks else ""
