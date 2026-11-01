"""LLM provider helpers (Anthropic-first, OE-compatible surface)."""
from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import settings

_DEEP_MODELS = {
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5-5",
}


def model_supports_deep_reasoning(model: str) -> bool:
    return model in _DEEP_MODELS or "opus" in model


def allowed_models() -> list[str]:
    return [
        settings.default_model,
        settings.routing_model,
        settings.deep_reasoning_model,
        "claude-haiku-5-5",
        "claude-sonnet-5-5",
        "claude-opus-5-5",
    ]


def allowed_models_for(_agent_id: str | None = None) -> list[str]:
    return allowed_models()


def model_options_for(_agent_id: str | None = None) -> list[dict[str, str]]:
    return [
        {
            "id": m,
            "provider": "anthropic",
            "provider_label": "Anthropic",
            "route": "direct",
            "label": m,
        }
        for m in allowed_models()
    ]


class _AnthropicProvider:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def messages_create(self, **kwargs: Any) -> Any:
        timeout = kwargs.pop("timeout", None)
        if timeout is not None:
            return await self._client.with_options(timeout=timeout).messages.create(**kwargs)
        return await self._client.messages.create(**kwargs)


def get_provider(_model: str | None = None) -> _AnthropicProvider:
    return _AnthropicProvider()
