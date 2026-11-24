"""Independent Companies for the Group HR Scorecard (attrition-focused roster)."""
from __future__ import annotations

from typing import Literal

Archetype = Literal["strong", "steady", "struggling", "early_stage"]

# (code, display name, stub archetype) — codes match API.md / ICHRATTRITION.
# Archetypes are unused for live attrition sync; kept for demo RNG compatibility.
LNT_COMPANIES: list[tuple[str, str, Archetype]] = [
    ("PTD", "Power Transmission & Distribution - IC", "steady"),
    ("TI", "Transportation Infrastructure IC", "steady"),
    ("RCF", "Residential, Commercial Buildings & Factories", "steady"),
    ("LTPO", "L&T Energy-CarbonLite Solutions", "steady"),
    ("GEO", "L&T - GeoStructure", "steady"),
    ("REN", "Renewables IC", "steady"),
    ("HCI", "Heavy Civil Infrastructure IC", "steady"),
    ("PAH", "Public Spaces, Airports & Health", "steady"),
    ("MMH", "Minerals & Metals", "steady"),
    ("DC", "Divisional Corporate", "steady"),
    ("HYOS", "L&T Energy Hydrocarbon - Onshore", "steady"),
    ("HYOF", "L&T Energy Hydrocarbon - Offshore", "steady"),
    ("DEIC", "L&T Precision Engineering & Systems IC", "steady"),
    ("MIPD", "Construction Equipment & Industrial Product Design Development", "steady"),
    ("RELT", "REALTY", "steady"),
    ("MRSF", "Modification Revamp and Upgradation Business", "steady"),
    ("HENG", "Heavy Engineering", "steady"),
    ("VALV", "L&T Valves Limited", "steady"),
    ("MRHL", "L & T Metro Rail (Hyderabad) Limited", "steady"),
    ("HYOW", "Offshore Wind Business", "steady"),
    ("LEDT", "EduTech", "early_stage"),
    ("IU72", "Larsen & Toubro – Vyoma", "early_stage"),
    ("HOSC", "Head Office", "steady"),
    ("LTST", "L&T Semiconductor Technologies Limited", "early_stage"),
    ("SWC", "Smart World and Communication", "steady"),
    ("LTGE", "Green Tech Limited", "early_stage"),
    ("SU", "L&T SuFin", "early_stage"),
    ("LTCG", "LARSEN & TOUBRO LIMITED, CONSTRUCTION", "steady"),
    ("WETD", "WETD", "steady"),
    ("WETI", "WETI", "steady"),
]

LNT_CODES: list[str] = [c for c, _, _ in LNT_COMPANIES]
LNT_BY_CODE: dict[str, tuple[str, Archetype]] = {c: (n, a) for c, n, a in LNT_COMPANIES}

# Legacy demo fixture folders (optional). New ICs have no seed packs.
FIXTURE_SLUGS: dict[str, str] = {}

GROUP_CHRO_USER_ID = "group-chro"
