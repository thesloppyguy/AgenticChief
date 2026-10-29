from __future__ import annotations

from abc import ABC, abstractmethod

from .raw import Raw


class IntegrationDisabled(RuntimeError):
    pass


class Extractor(ABC):
    source: str
    mode: str  # "live" | "stub"
    kpis: tuple[str, ...]

    def lineage_for(self, kpi: str) -> dict:
        """Extra lineage to store with a KPI's records (e.g. which capability and version supplied it)."""
        return {}

    @abstractmethod
    def fetch(self, company_code: str, period: str) -> dict[str, Raw]:
        """Raw counts per KPI key. A KPI left out of the result has no data for that company/period."""
