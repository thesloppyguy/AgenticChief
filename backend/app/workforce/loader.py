"""Load deterministic workforce YAML from seed/lnt_group/workforce/."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.fixtures.paths import GROUP_DIR

WORKFORCE_DIR = GROUP_DIR / "workforce"
SECTIONS = ("pulse", "skills", "succession", "actions")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=8)
def load_section(name: str) -> dict[str, Any]:
    key = name.strip().lower()
    if key not in SECTIONS:
        raise ValueError(f"unknown workforce section '{name}'")
    return dict(_read_yaml(WORKFORCE_DIR / f"{key}.yaml"))


def clear_cache() -> None:
    load_section.cache_clear()


def pulse() -> dict[str, Any]:
    return load_section("pulse")


def skills() -> dict[str, Any]:
    return load_section("skills")


def succession() -> dict[str, Any]:
    return load_section("succession")


def draft_actions() -> dict[str, Any]:
    return load_section("actions")


def artifact_for(section: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Structured chart payload for chat SSE (optional)."""
    if section == "pulse":
        cells = payload.get("cells") or []
        return {
            "kind": "kpi_bars",
            "title": "Workforce pulse",
            "source": "workforce.pulse",
            "export_key": "workforce_pulse",
            "schedule_key": "workforce_brief",
            "items": [
                {
                    "label": c.get("label") or c.get("key"),
                    "value": c.get("value"),
                    "unit": c.get("unit") or "",
                }
                for c in cells
            ],
        }
    if section == "skills":
        domains = payload.get("domains") or []
        return {
            "kind": "skills_demand_supply",
            "title": "Future skills · demand vs supply",
            "source": "workforce.skills",
            "export_key": "workforce_skills",
            "schedule_key": "workforce_brief",
            "domains": [
                {
                    "label": d.get("label"),
                    "demand": d.get("demand"),
                    "supply": d.get("supply"),
                    "gap": d.get("gap"),
                    "path": d.get("path"),
                }
                for d in domains
            ],
        }
    if section == "succession":
        rows = payload.get("by_function") or []
        return {
            "kind": "succession_stack",
            "title": "Succession coverage by function",
            "source": "workforce.succession",
            "export_key": "workforce_succession",
            "schedule_key": "workforce_brief",
            "functions": [
                {
                    "function": r.get("function"),
                    "ready_now": r.get("ready_now"),
                    "ready_1_2y": r.get("ready_1_2y"),
                    "no_successor": r.get("no_successor"),
                }
                for r in rows
            ],
        }
    if section == "actions":
        drafts = payload.get("drafts") or []
        return {
            "kind": "table",
            "title": "Draft CHRO actions",
            "source": "workforce.actions",
            "export_key": "workforce_actions",
            "schedule_key": None,
            "columns": ["key", "title", "severity", "sla"],
            "rows": [
                [d.get("key"), d.get("title"), d.get("severity"), d.get("sla")]
                for d in drafts
            ],
        }
    return None
