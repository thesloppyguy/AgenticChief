from app.agents.base import BaseAgent
from app.config import get_settings


class SalesAgent(BaseAgent):
    name = "sales"
    domain = "sales"
    visibility = "core"

    @property
    def model(self) -> str:  # type: ignore[override]
        return get_settings().default_model

    def get_system_prompt(self) -> str:
        from app.prompts.domain_prompts import SALES_PROMPT

        return SALES_PROMPT
