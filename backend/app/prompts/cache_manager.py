"""Stable Anthropic prompt-cache system blocks for the Executive."""
from __future__ import annotations

from typing import Any

from app.agents.overrides import append_instructions
from app.company.profile import CompanyProfile, load_profile
from app.core.config import settings
from app.prompts.executive_persona import (
    EXECUTIVE_PERSONA_PROMPT,
    MCP_ADDENDUM,
    TOOL_BUILDING_ADDENDUM,
    WEB_SEARCH_ADDENDUM,
)

KNOWLEDGE_INDEX_SUMMARY = (
    "You have access to a curated knowledge base covering executive frameworks across "
    "strategy, finance, HR, legal, operations, marketing, product, sales, and board "
    "communications, plus the Group HR scorecard. When relevant, retrieve frameworks "
    "and company documents to ground your analysis."
)


def build_system_blocks(
    *,
    persona_override: str | None = None,
    persona_instructions: str | None = None,
    mcp_enabled: bool = False,
    company_profile: CompanyProfile | None = None,
) -> list[dict[str, Any]]:
    """Block 0: persona + knowledge index (always). Block 1: company profile (if set)."""
    base = persona_override or EXECUTIVE_PERSONA_PROMPT.replace(
        "{VOICE_PERSONA}", "Direct, calm, decisive."
    )
    base = append_instructions(base, persona_instructions)
    if settings.enable_web_search:
        base = base + WEB_SEARCH_ADDENDUM
    if mcp_enabled:
        base = base + MCP_ADDENDUM
    base = base + TOOL_BUILDING_ADDENDUM
    base = (
        base
        + f"\n\nThe user's local timezone is {settings.user_timezone} (IANA)."
        + f"\n\n{KNOWLEDGE_INDEX_SUMMARY}"
    )
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": base,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    profile = company_profile if company_profile is not None else load_profile()
    prompt = profile.to_prompt_block()
    if prompt:
        blocks.append(
            {
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }
        )
    return blocks
