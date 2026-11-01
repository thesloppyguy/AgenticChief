"""Lightweight triage specialist (simplified OE port without OE alert models)."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.config import get_settings

_TRIAGE_PROMPT = """You are the Chief of Staff triage agent. Decide whether an inbound
event is significant enough to surface to leadership. Be concise and conservative:
routine FYI traffic is not an alert; deadlines, risks, decisions, and escalations are.
"""


class TriageAgent(BaseAgent):
    name = "triage"
    domain = "operations"
    visibility = "internal"
    use_deep_reasoning = False

    @property
    def model(self) -> str:  # type: ignore[override]
        return get_settings().routing_model

    def get_system_prompt(self) -> str:
        return _TRIAGE_PROMPT
