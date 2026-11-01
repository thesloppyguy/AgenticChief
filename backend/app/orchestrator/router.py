"""Specialist registry and parallel consult (OpenExecutive port)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.base import BaseAgent
from app.agents.board_comms import BoardCommsAgent
from app.agents.finance import FinanceAgent
from app.agents.hr_talent import HRAgent
from app.agents.legal import LegalAgent
from app.agents.marketing import MarketingAgent
from app.agents.operations import OperationsAgent
from app.agents.product import ProductAgent
from app.agents.sales import SalesAgent
from app.agents.strategy import StrategyAgent
from app.agents.triage import TriageAgent
from app.knowledge.retriever import retrieve

logger = logging.getLogger(__name__)

SPECIALIST_REGISTRY: dict[str, BaseAgent] = {
    "cso": StrategyAgent(),
    "cfo": FinanceAgent(),
    "chro": HRAgent(),
    "gc": LegalAgent(),
    "coo": OperationsAgent(),
    "cmo": MarketingAgent(),
    "cpo": ProductAgent(),
    "sales": SalesAgent(),
    "board_comms": BoardCommsAgent(),
    "triage": TriageAgent(),
}

SPECIALIST_DESCRIPTIONS = {
    "cso": "Chief Strategy Officer — competitive analysis, M&A, market positioning, scenario planning, OKRs",
    "cfo": "Chief Financial Officer — financial modeling, unit economics, fundraising, cash flow, board finance",
    "chro": "Chief HR/People Officer — hiring, compensation, performance management, culture, org design",
    "gc": "General Counsel — contracts, IP, employment law basics, compliance (with appropriate disclaimers)",
    "coo": "Chief Operating Officer — process design, vendor management, operational scaling, metrics",
    "cmo": "Chief Marketing Officer — GTM strategy, brand, messaging, PR, crisis communications",
    "cpo": "Chief Product Officer — product roadmap, prioritization frameworks, product strategy",
    "sales": "Head of Sales — pipeline and qualification, discovery, founder-led sales, pricing, proposals, forecasting",
    "board_comms": "Board Communications Director — board decks, investor relations, governance",
    "triage": "Chief of Staff — evaluates inbound events for significance and decides alerting",
}

SPECIALIST_SHORT = {
    "cso": "strategy, competition, M&A, positioning, OKRs",
    "cfo": "finance, unit economics, fundraising, cash flow",
    "chro": "hiring, compensation, performance, culture, org design",
    "gc": "contracts, IP, employment law, compliance",
    "coo": "processes, vendors, scaling, operating metrics",
    "cmo": "GTM, brand, messaging, PR, crisis communications",
    "cpo": "roadmap, prioritization, product strategy",
    "sales": "pipeline, discovery, pricing and discounting, proposals, forecasting",
    "board_comms": "board decks, investor relations, governance",
    "triage": "whether an inbound event is significant",
}

_SPECIALIST_OPTIONS = "; ".join(f"{k} ({v})" for k, v in SPECIALIST_SHORT.items())

SPECIALIST_TOOLS: list[dict[str, Any]] = [
    {
        "name": "consult_specialist",
        "description": (
            "Consult a specialist executive for analysis in their area whenever a "
            "question asks for judgment. Call several in parallel for cross-domain questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialist": {
                    "type": "string",
                    "enum": sorted(SPECIALIST_REGISTRY.keys()),
                    "description": f"Which specialist to consult: {_SPECIALIST_OPTIONS}.",
                },
                "query": {
                    "type": "string",
                    "description": "The precise question or task for the specialist.",
                },
                "context": {
                    "type": "string",
                    "description": "Context from the conversation the specialist needs.",
                },
            },
            "required": ["specialist", "query"],
        },
    }
]


async def consult_one(
    specialist: str,
    query: str,
    context: str = "",
    *,
    company_stage: str = "",
    episodic_context: str = "",
    retrieved_knowledge: str = "",
) -> dict[str, Any]:
    agent = SPECIALIST_REGISTRY.get(specialist)
    if agent is None:
        return {"specialist": specialist, "error": f"Unknown specialist '{specialist}'"}
    try:
        knowledge = retrieved_knowledge
        if not knowledge:
            knowledge = await asyncio.to_thread(
                retrieve, query, specialist_name=specialist
            )
        text = await agent.analyze(
            query=query,
            context=context,
            retrieved_knowledge=knowledge,
            episodic_context=episodic_context,
            company_stage=company_stage,
        )
        return {"specialist": specialist, "analysis": text}
    except Exception as exc:
        logger.exception("specialist %s failed", specialist)
        return {
            "specialist": specialist,
            "error": f"{type(exc).__name__}: {exc}",
            "analysis": (
                f"The {specialist} specialist is temporarily unavailable. "
                "Continue with other specialists' analyses."
            ),
        }


async def route_parallel(
    calls: list[dict[str, Any]],
    *,
    company_stage: str = "",
    episodic_context: str = "",
) -> list[dict[str, Any]]:
    if not company_stage:
        try:
            from app.company.profile import load_profile

            company_stage = load_profile().stage or ""
        except Exception:
            company_stage = ""

    async def _one(c: dict[str, Any]) -> dict[str, Any]:
        specialist = c.get("specialist", "")
        query = c.get("query", "")
        knowledge = await asyncio.to_thread(retrieve, query, specialist_name=specialist)
        return await consult_one(
            specialist,
            query,
            c.get("context", ""),
            company_stage=company_stage,
            episodic_context=episodic_context,
            retrieved_knowledge=knowledge,
        )

    return list(await asyncio.gather(*[_one(c) for c in calls]))
