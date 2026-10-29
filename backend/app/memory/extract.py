"""Decide what, if anything, the Copilot should remember from one exchange. Uses the small fast model."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import settings

DOMAINS = Literal["general", "hiring", "performance", "learning", "talent", "engagement", "retention", "data", "governance"]
MAX_INPUT = 20_000

SYSTEM = """You decide what an HR analytics assistant should REMEMBER from one exchange with a senior user.

Remember only things worth knowing in a future session, in one of three kinds:
- decision: something the user decided or committed to (e.g. "pause hiring in IC022 until Q3").
- initiative: a piece of work the user started or plans (e.g. "running a retention review for the Retention pillar").
- advice: a specific recommendation the assistant gave that the user accepted or asked to follow.

Do NOT remember: greetings, thanks, clarifying questions, pure data lookups ("what is the group score"),
explanations of how something is calculated, scores or figures by themselves, or anything the user did not
commit to. Do not record personal details about individual employees. Refer to companies by their codes.
If nothing qualifies, return an empty list. This is the usual case: be conservative.
Write each summary as one short, self-contained sentence (under 250 characters) that makes sense out of context."""


class MemoryItem(BaseModel):
    kind: Literal["decision", "initiative", "advice"]
    domain: DOMAINS = "general"
    summary: str = Field(min_length=8, max_length=300)


class MemoryBatch(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list, max_length=5)


async def extract(client: Any, user_message: str, assistant_text: str) -> list[MemoryItem]:
    """Never raises: memory is a convenience and must not affect the chat that produced it."""
    try:
        resp = await client.messages.parse(
            model=settings.routing_model, max_tokens=2000, system=SYSTEM,
            messages=[{"role": "user", "content": f"<user>\n{user_message[:MAX_INPUT]}\n</user>\n<assistant>\n{assistant_text[:MAX_INPUT]}\n</assistant>"}],
            output_format=MemoryBatch)
        if getattr(resp, "stop_reason", None) == "refusal" or resp.parsed_output is None:
            return []
        return list(resp.parsed_output.items)
    except Exception:  # noqa: BLE001
        return []
