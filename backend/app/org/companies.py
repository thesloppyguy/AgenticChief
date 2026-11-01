"""L&T Group Independent Companies for the Group HR Scorecard."""
from __future__ import annotations

from typing import Literal

Archetype = Literal["strong", "steady", "struggling", "early_stage"]

# (code, display name, stub archetype) — archetypes give a realistic Group amber/red mix.
LNT_COMPANIES: list[tuple[str, str, Archetype]] = [
    ("LTF", "L&T Finance", "steady"),
    ("LTMR", "L&T Metro Rail", "struggling"),
    ("LTR", "L&T Realty", "steady"),
    ("LTTS", "L&T Technology Services", "strong"),
    ("LTIM", "LTIMindtree", "strong"),
]

LNT_CODES: list[str] = [c for c, _, _ in LNT_COMPANIES]
LNT_BY_CODE: dict[str, tuple[str, Archetype]] = {c: (n, a) for c, n, a in LNT_COMPANIES}

# Fixture folder slug under seed/companies/
FIXTURE_SLUGS: dict[str, str] = {
    "LTF": "lnt_finance",
    "LTMR": "lnt_metro_rail",
    "LTR": "lnt_realty",
    "LTTS": "lnt_technology_services",
    "LTIM": "ltimindtree",
}

GROUP_CHRO_USER_ID = "group-chro"
