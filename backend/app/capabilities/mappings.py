"""Approved KPI -> capability mappings, and the extractor that uses them.

Only an approved mapping on a published, non-deprecated, non-removed, READ capability is ever used for
production data. Anything else is ignored, so unreviewed tools cannot feed a score.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Capability, CapabilityVersion, Connection, KpiMapping
from app.ingestion.base import Extractor
from app.ingestion.live import dig
from app.ingestion.raw import SPECS, Raw

from .invoke import invoke


@dataclass(frozen=True)
class ActiveMapping:
    kpi_key: str
    capability_key: str
    version: int
    connection_id: int
    implementation: dict
    input_schema: dict
    field_map: dict
    arg_template: dict


def active_mappings(db: Session) -> list[ActiveMapping]:
    rows = db.execute(
        select(KpiMapping, Capability).join(Capability, Capability.id == KpiMapping.capability_id).where(
            KpiMapping.status == "approved", Capability.published_version.is_not(None),
            Capability.removed.is_(False), Capability.deprecated.is_(False))).all()
    out = []
    for m, cap in rows:
        ver = db.scalar(select(CapabilityVersion).where(CapabilityVersion.capability_id == cap.id,
                                                        CapabilityVersion.version == cap.published_version))
        conn = db.get(Connection, cap.connection_id)
        if ver is None or ver.risk != "read" or conn is None or not conn.active or m.kpi_key not in SPECS:
            continue
        out.append(ActiveMapping(m.kpi_key, cap.key, ver.version, cap.connection_id, ver.implementation,
                                 ver.input_schema, m.field_map, m.arg_template))
    return out


def mapped_kpis(db: Session) -> frozenset[str]:
    return frozenset(m.kpi_key for m in active_mappings(db))


def _coerce(value, prop: dict):
    t = prop.get("type")
    try:
        if t == "integer":
            return int(value)
        if t == "number":
            return float(value)
    except (TypeError, ValueError):
        pass
    return value


class RegistryExtractor(Extractor):
    """Pulls raw counts by calling the mapped capability, then lets the usual formulas run on them."""

    source = "registry"
    mode = "registry"

    def __init__(self, db: Session, mappings: list[ActiveMapping]):
        self._db = db
        self._by_kpi = {m.kpi_key: m for m in mappings}
        self.kpis = tuple(sorted(self._by_kpi))

    def lineage_for(self, kpi: str) -> dict:
        m = self._by_kpi[kpi]
        return {"capability": m.capability_key, "capability_version": m.version}

    def fetch(self, company_code: str, period: str) -> dict[str, Raw]:
        year, month = period.split("-")
        ctx = {"company_code": company_code, "period": period, "year": year, "month": month}
        out: dict[str, Raw] = {}
        for kpi, m in self._by_kpi.items():
            props = m.input_schema.get("properties", {})
            args = {k: _coerce(v.format_map(ctx) if isinstance(v, str) else v, props.get(k, {}))
                    for k, v in m.arg_template.items()}
            conn = self._db.get(Connection, m.connection_id)
            result = invoke(self._db, conn, m.implementation, m.input_schema, args)
            raw: Raw = {}
            for field in SPECS[kpi].fields:
                val = dig(result, m.field_map.get(field, ""))
                raw[field] = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None
            if any(v is not None for v in raw.values()):  # the source had nothing for this company: no value
                out[kpi] = raw
        return out
