"""Decide, per source, whether data comes from the live integration, stub data, or nowhere."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.capabilities.mappings import RegistryExtractor, active_mappings, mapped_kpis
from app.core.config import Settings
from app.core.config import settings as default_settings

from .ai_generator import load_fixture
from .base import Extractor
from .live import RestExtractor, load_mapping
from .sources import SOURCE_KPIS, SOURCE_LABELS
from .stub import StubExtractor


def source_mode(source: str, cfg: Settings) -> str:
    if cfg.integration(source).enabled:
        return "live"
    return "stub" if cfg.stub_data_enabled else "disabled"


@lru_cache(maxsize=4)
def _fixture(path: str, mtime: float):
    return load_fixture(path)


def build_extractors(cfg: Settings = default_settings, db: Session | None = None) -> dict[str, Extractor]:
    """Only sources that can supply data. Disabled sources are absent -> their KPIs have no data.

    With a database session, KPIs that have an approved registry mapping are taken over by the registry
    extractor and removed from the source that used to supply them (stub or live)."""
    p = Path(cfg.stub_data_path)
    out: dict[str, Extractor] = {}
    for source in SOURCE_KPIS:
        mode = source_mode(source, cfg)
        if mode == "live":
            out[source] = RestExtractor(source, cfg.integration(source))
        elif mode == "stub":
            fixture = _fixture(str(p), p.stat().st_mtime if p.exists() else 0.0)
            out[source] = StubExtractor(source, fixture)
    if db is not None:
        mappings = active_mappings(db)
        taken = {m.kpi_key for m in mappings}
        for name, ex in list(out.items()):
            ex.kpis = tuple(k for k in ex.kpis if k not in taken)
            if not ex.kpis:
                del out[name]
        if mappings:
            out["registry"] = RegistryExtractor(db, mappings)
    return out


def source_no_source_kpis(source: str, cfg: Settings = default_settings) -> frozenset[str]:
    """KPIs of this source that nothing can supply: all of them if the source is disabled, or the
    ones missing from a live source's mapping file."""
    kpis = set(SOURCE_KPIS[source])
    mode = source_mode(source, cfg)
    if mode == "disabled":
        return frozenset(kpis)
    if mode == "live":
        return frozenset(kpis - set(load_mapping(cfg.integration(source).mapping_file)))
    return frozenset()


def no_source_kpis(cfg: Settings = default_settings, db: Session | None = None) -> frozenset[str]:
    """KPIs nothing can supply: unsupplied by their source AND not covered by an approved registry mapping."""
    base = frozenset().union(*(source_no_source_kpis(s, cfg) for s in SOURCE_KPIS))
    return base - mapped_kpis(db) if db is not None else base


def describe(cfg: Settings = default_settings, db: Session | None = None) -> list[dict]:
    p = Path(cfg.stub_data_path)
    mapped = mapped_kpis(db) if db is not None else frozenset()
    rows = [
        {
            "source": s, "label": SOURCE_LABELS[s], "mode": source_mode(s, cfg),
            "live_enabled": cfg.integration(s).enabled, "kpis": list(SOURCE_KPIS[s]),
            "stub_fixture": p.exists(),
            "no_source_kpis": sorted(source_no_source_kpis(s, cfg) - mapped),
            "taken_over_by_registry": sorted(set(SOURCE_KPIS[s]) & mapped),
        }
        for s in SOURCE_KPIS
    ]
    if mapped:
        rows.append({"source": "registry", "label": SOURCE_LABELS["registry"], "mode": "registry",
                     "live_enabled": False, "kpis": sorted(mapped), "stub_fixture": False,
                     "no_source_kpis": [], "taken_over_by_registry": []})
    return rows
