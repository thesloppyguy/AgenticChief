"""Executive tools for searching and loading Markdown skills."""
from __future__ import annotations

import json
from typing import Any

from app.knowledge import skills_index, skills_repo
from app.knowledge.chroma_store import ChromaDBStore
from app.knowledge.skills_repo import SkillNotFoundError

SKILL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_skills",
        "description": (
            "Semantically search reusable playbooks/skills by what you need to do. "
            "Returns metadata only; call load_skill for the full procedure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "n_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "load_skill",
        "description": "Load the full Markdown body of a skill/playbook by exact name.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def _store() -> ChromaDBStore:
    from app.config import get_settings

    return ChromaDBStore(persist_directory=get_settings().vector_store_path)


def handle_search_skills(args: dict[str, Any]) -> str:
    hits = skills_index.search_skills(
        args["query"],
        _store(),
        n_results=int(args.get("n_results") or 5),
    )
    return json.dumps({"skills": hits}, ensure_ascii=False)


def handle_load_skill(args: dict[str, Any]) -> str:
    try:
        skill = skills_repo.get_skill(args["name"])
    except SkillNotFoundError as e:
        return json.dumps({"error": str(e)})
    return json.dumps(skills_repo.skill_to_dict(skill), ensure_ascii=False)
