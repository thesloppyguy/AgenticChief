"""ChromaDB integration for the skills library (OpenExecutive port)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.chroma_store import ChromaDBStore
from app.knowledge.skills import Skill, SkillParseError, SkillSource, parse_skill_file

logger = logging.getLogger(__name__)

SKILLS_COLLECTION = "skills"
BUILTIN_SKILLS_PATH = Path(__file__).resolve().parent / "builtin" / "skills"
HIDDEN_SKILLS_FILENAME = ".hidden.yaml"


def _company_skills_path() -> Path:
    from app.config import get_settings

    return get_settings().company_skills_path


def hidden_builtin_names() -> set[str]:
    path = _company_skills_path() / HIDDEN_SKILLS_FILENAME
    if not path.exists():
        return set()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Ignoring unreadable hidden-skills file %s: %s", path, e)
        return set()
    names = data.get("hidden") if isinstance(data, dict) else None
    if not isinstance(names, list):
        return set()
    return {n for n in names if isinstance(n, str)}


def write_hidden_builtin_names(names: set[str]) -> None:
    path = _company_skills_path() / HIDDEN_SKILLS_FILENAME
    if not names:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"hidden": sorted(names)}, default_flow_style=False),
        encoding="utf-8",
    )


def company_skill_names() -> set[str]:
    root = _company_skills_path()
    if not root.exists():
        return set()
    names: set[str] = set()
    for path in root.rglob("*.md"):
        try:
            names.add(parse_skill_file(path, source="company").frontmatter.name)
        except SkillParseError:
            continue
    return names


def _skill_id(name: str, source: SkillSource) -> str:
    return f"skill::{source}::{name}"


def _skill_doc_text(skill: Skill) -> str:
    fm = skill.frontmatter
    return f"{fm.name}\n{fm.description}\n{fm.when_to_use}"


def _index_metadata(skill: Skill) -> dict[str, Any]:
    fm = skill.frontmatter
    return {
        "name": fm.name,
        "category": fm.category,
        "source": skill.source,
        "description": fm.description,
        "when_to_use": fm.when_to_use,
        "filename": Path(skill.path).name,
        "path": skill.path,
    }


def index_skill(skill: Skill, store: ChromaDBStore) -> None:
    store.add_documents(
        texts=[_skill_doc_text(skill)],
        metadatas=[_index_metadata(skill)],
        ids=[_skill_id(skill.frontmatter.name, skill.source)],
        collection=SKILLS_COLLECTION,
    )


def delete_skill_index(name: str, source: SkillSource, store: ChromaDBStore) -> None:
    store.delete_documents(
        collection=SKILLS_COLLECTION,
        where={"$and": [{"name": name}, {"source": source}]},
    )


def _keyword_search(
    query: str, n_results: int, source_filter: SkillSource | None
) -> list[dict[str, Any]]:
    """Fallback when Chroma embeddings are unavailable (first boot / offline)."""
    from app.knowledge.skills_repo import list_skills

    tokens = [t for t in query.lower().split() if t]
    scored: list[tuple[int, dict[str, Any]]] = []
    for skill in list_skills():
        if source_filter and skill.source != source_filter:
            continue
        fm = skill.frontmatter
        hay = f"{fm.name} {fm.description} {fm.when_to_use} {fm.category}".lower()
        score = sum(1 for t in tokens if t in hay) if tokens else 1
        if score:
            scored.append(
                (
                    score,
                    {
                        "name": fm.name,
                        "category": fm.category,
                        "description": fm.description,
                        "when_to_use": fm.when_to_use,
                        "source": skill.source,
                        "score": float(score),
                    },
                )
            )
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return [h for _, h in scored[:n_results]]


def search_skills(
    query: str,
    store: ChromaDBStore,
    n_results: int = 5,
    source_filter: SkillSource | None = None,
) -> list[dict[str, Any]]:
    if n_results <= 0:
        return []
    try:
        col = store._get_or_create_collection(SKILLS_COLLECTION)
        count = col.count()
        if count == 0:
            return _keyword_search(query, n_results, source_filter)
        where: dict[str, Any] | None = {"source": source_filter} if source_filter else None
        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, count),
            "include": ["metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where
        results = col.query(**query_kwargs)
        hits: list[dict[str, Any]] = []
        if results["metadatas"] and results["metadatas"][0]:
            for meta, dist in zip(
                results["metadatas"][0],
                results["distances"][0],
                strict=False,
            ):
                score = max(0.0, 1.0 - float(dist))
                hits.append(
                    {
                        "name": meta.get("name", ""),
                        "category": meta.get("category", ""),
                        "description": meta.get("description", ""),
                        "when_to_use": meta.get("when_to_use", ""),
                        "source": meta.get("source", ""),
                        "score": round(score, 4),
                    }
                )
        return hits
    except Exception:
        logger.exception("Chroma skill search failed; using keyword fallback")
        return _keyword_search(query, n_results, source_filter)


def _iter_skill_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.md"))


def sync_builtin_skill_index(store: ChromaDBStore, force: bool = False) -> int:
    shadowed = hidden_builtin_names() | company_skill_names()
    wanted: dict[str, Skill] = {}
    for path in _iter_skill_files(BUILTIN_SKILLS_PATH):
        try:
            skill = parse_skill_file(path, source="builtin")
        except SkillParseError as e:
            logger.warning("Skipping malformed skill %s: %s", path, e)
            continue
        if skill.frontmatter.name not in shadowed:
            wanted[_skill_id(skill.frontmatter.name, "builtin")] = skill

    existing = {
        sid: meta
        for sid, meta in store.iter_chunk_metadata(SKILLS_COLLECTION)
        if meta.get("source") == "builtin"
    }
    store.delete_by_ids(SKILLS_COLLECTION, [sid for sid in existing if sid not in wanted])

    count = 0
    for sid, skill in wanted.items():
        meta = existing.get(sid)
        stale = meta is None or any(
            meta.get(k) != v for k, v in _index_metadata(skill).items()
        )
        if force or stale:
            index_skill(skill, store)
            count += 1
    return count


def seed_builtin_skills(store: ChromaDBStore | None = None, force: bool = False) -> int:
    if store is None:
        from app.config import get_settings

        store = ChromaDBStore(persist_directory=get_settings().vector_store_path)
    try:
        return sync_builtin_skill_index(store, force=force)
    except Exception:
        logger.exception(
            "skills Chroma seed failed; filesystem skills remain available via list/get"
        )
        return 0
