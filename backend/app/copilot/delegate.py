"""Specialist consultation shim (replaces asset-based delegation)."""
from __future__ import annotations

from typing import Any

DEFINITION = {
    "name": "delegate",
    "description": (
        "Deprecated: prefer consult_specialist via the Executive. "
        "Kept so older tool allowlists do not break."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "specialist": {"type": "string"},
            "query": {"type": "string"},
        },
        "required": ["specialist", "query"],
    },
}


def new_budget(_roster: list[str] | None = None) -> dict[str, Any] | None:
    return None
