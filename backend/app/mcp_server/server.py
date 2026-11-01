"""MCP server mounted at /mcp (OpenExecutive-style, MCP 2.x MCPServer)."""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from app.orchestrator.router import SPECIALIST_DESCRIPTIONS, SPECIALIST_REGISTRY, consult_one

logger = logging.getLogger(__name__)

SpecialistKey = Literal[
    "board_comms", "cfo", "chro", "cmo", "coo", "cpo", "cso", "gc", "sales", "triage"
]

mcp = MCPServer(
    name="agenticchief",
    instructions=(
        "AgenticChief MCP server: consult executive specialists, search skills, "
        "and list specialists. Read-oriented by default."
    ),
)


@mcp.resource("agenticchief://specialists")
def specialists_resource() -> str:
    return json.dumps(
        {
            k: {"description": SPECIALIST_DESCRIPTIONS.get(k, ""), "domain": a.domain}
            for k, a in SPECIALIST_REGISTRY.items()
        },
        indent=2,
    )


@mcp.tool()
async def consult_specialist(specialist: SpecialistKey, query: str, context: str = "") -> str:
    """Consult a domain specialist and return their analysis."""
    result = await consult_one(specialist, query, context)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def search_skills(query: str, n_results: int = 5) -> str:
    """Search Markdown playbooks/skills by meaning."""
    from app.orchestrator.skills_tools import handle_search_skills

    return handle_search_skills({"query": query, "n_results": n_results})


@mcp.tool()
def load_skill(name: str) -> str:
    """Load a skill/playbook body by exact name."""
    from app.orchestrator.skills_tools import handle_load_skill

    return handle_load_skill({"name": name})


@mcp.tool()
def list_specialists() -> str:
    """List consultable specialists."""
    return json.dumps(
        [{"key": k, "description": v} for k, v in SPECIALIST_DESCRIPTIONS.items()],
        ensure_ascii=False,
    )


def mount(app: Any) -> None:
    """Mount the streamable HTTP MCP app at /mcp."""
    try:
        asgi = mcp.streamable_http_app()
        app.mount("/mcp", asgi)
        logger.info("Mounted MCP server at /mcp")
    except Exception:
        logger.exception("Failed to mount MCP server at /mcp")
