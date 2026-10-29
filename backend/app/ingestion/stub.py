from __future__ import annotations

import hashlib
import random

from app.scoring.fiscal import fiscal_index

from .base import Extractor
from .raw import SPECS, Raw
from .sources import SOURCE_KPIS
from .stubgen import CompanyRaw, synthetic_company, to_kpi_raw

_BINARY = {"ppw_on_time", "training_calendar"}


def _jitter(kpi: str, raw: Raw, rng: random.Random) -> Raw:
    """Small month-to-month drift so periods differ; never breaks numerator <= denominator."""
    if kpi in _BINARY:
        return raw
    f = rng.uniform(0.97, 1.03)
    spec = SPECS[kpi]
    out = dict(raw)
    if spec.kind == "value":
        name = spec.fields[0]
        if out.get(name) is not None:
            out[name] = round(out[name] * f, 2)  # type: ignore[operator]
            if kpi == "l1_feedback":
                out[name] = min(5.0, max(1.0, out[name]))  # type: ignore[type-var]
    else:
        num, den = spec.fields
        if out.get(num) is not None and out.get(den) is not None:
            out[num] = min(out[den], round(out[num] * f))  # type: ignore[type-var,operator]
    return out


class StubExtractor(Extractor):
    """Serves generated data in place of a source system. Lineage marks every value as stub."""

    mode = "stub"

    def __init__(self, source: str, companies: dict[str, CompanyRaw] | None = None):
        self.source = source
        self.kpis = SOURCE_KPIS[source]
        self._companies = companies or {}

    def fetch(self, company_code: str, period: str) -> dict[str, Raw]:
        base = self._companies.get(company_code) or synthetic_company(company_code)
        seed = int.from_bytes(hashlib.sha256(f"{company_code}|{period}".encode()).digest()[:8], "big")
        rng = random.Random(seed)
        kpi_raw = to_kpi_raw(base)
        out = {k: _jitter(k, kpi_raw[k], rng) for k in self.kpis}
        if "training_calendar" in out and fiscal_index(int(period.split("-")[1])) < 6:
            # Only the April-September calendar can exist before October.
            out["training_calendar"] = {"value": min(out["training_calendar"]["value"] or 0, 1)}
        return out
