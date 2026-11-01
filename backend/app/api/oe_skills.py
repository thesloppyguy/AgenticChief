"""Filesystem skills API (OpenExecutive port)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import Principal, get_principal, require_admin
from app.knowledge import skills_index, skills_repo
from app.knowledge.chroma_store import ChromaDBStore
from app.knowledge.skills import SKILL_CATEGORIES, SkillParseError
from app.knowledge.skills_repo import SkillConflictError, SkillNotFoundError
from app.config import get_settings

router = APIRouter(prefix="/skills", tags=["skills"])


def _store() -> ChromaDBStore:
    return ChromaDBStore(persist_directory=get_settings().vector_store_path)


class SkillWrite(BaseModel):
    name: str
    description: str
    when_to_use: str
    category: str
    body: str = Field(..., min_length=1)


@router.get("")
def list_skills(
    include_hidden: bool = False, _who: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    return [
        skills_repo.skill_to_dict(s, include_body=False)
        for s in skills_repo.list_skills(include_hidden=include_hidden)
    ]


@router.get("/categories")
def categories(_who: Principal = Depends(get_principal)) -> list[str]:
    return list(SKILL_CATEGORIES)


@router.get("/search")
def search(
    q: str, n: int = 5, _who: Principal = Depends(get_principal)
) -> list[dict[str, Any]]:
    return skills_index.search_skills(q, _store(), n_results=n)


@router.get("/{name}")
def get_skill(
    name: str, include_hidden: bool = False, _who: Principal = Depends(get_principal)
) -> dict[str, Any]:
    try:
        return skills_repo.skill_to_dict(
            skills_repo.get_skill(name, include_hidden=include_hidden)
        )
    except SkillNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except SkillParseError as e:
        raise HTTPException(400, str(e)) from e


@router.post("")
def create_skill(body: SkillWrite, _who: Principal = Depends(require_admin)) -> dict[str, Any]:
    try:
        skill = skills_repo.create_skill(
            body.name,
            body.description,
            body.when_to_use,
            body.category,
            body.body,
            _store(),
        )
    except SkillConflictError as e:
        raise HTTPException(409, str(e)) from e
    except SkillParseError as e:
        raise HTTPException(400, str(e)) from e
    return skills_repo.skill_to_dict(skill)


@router.put("/{name}")
def update_skill(
    name: str, body: SkillWrite, _who: Principal = Depends(require_admin)
) -> dict[str, Any]:
    try:
        skill = skills_repo.update_skill(
            name,
            body.description,
            body.when_to_use,
            body.category,
            body.body,
            _store(),
        )
    except SkillNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except SkillParseError as e:
        raise HTTPException(400, str(e)) from e
    return skills_repo.skill_to_dict(skill)


@router.delete("/{name}")
def delete_skill(name: str, _who: Principal = Depends(require_admin)) -> dict[str, str]:
    try:
        outcome = skills_repo.delete_skill(name, _store())
    except SkillNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return {"status": outcome}


@router.post("/{name}/restore")
def restore_skill(name: str, _who: Principal = Depends(require_admin)) -> dict[str, Any]:
    try:
        skill = skills_repo.restore_skill(name, _store())
    except SkillNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except SkillParseError as e:
        raise HTTPException(400, str(e)) from e
    return skills_repo.skill_to_dict(skill)
