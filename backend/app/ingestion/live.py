"""Generic REST/OData extractor for the real source systems. DISABLED unless its flag is on.

NOT VERIFIED AGAINST A REAL TENANT: no endpoint, entity or field names are hard-coded. What each KPI
reads is declared in a JSON mapping file (settings: integrations.<source>.mapping_file), e.g.

  {"kra_submission": {
      "path": "/odata/v2/SomeEntity",
      "params": {"$filter": "company eq '{company_code}' and period eq '{period}'"},
      "result_path": "d.results.0",
      "fields": {"submitted": "SubmittedCount", "eligible": "EligibleCount"}}}

A KPI without a mapping entry has no source and is simply not returned. Template variables:
{company_code}, {period}, {year}, {month}.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import IntegrationConfig

from .base import Extractor, IntegrationDisabled
from .raw import SPECS, Raw
from .sources import SOURCE_KPIS


def dig(obj: Any, path: str) -> Any:
    """Follow 'a.b.0.c' through dicts and lists; None if anything is missing."""
    for part in path.split(".") if path else []:
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
        if obj is None:
            return None
    return obj


def load_mapping(path: str | None) -> dict[str, dict]:
    """KPI -> endpoint/field mapping. No file, or an unreadable one, means nothing is mapped."""
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


class RestExtractor(Extractor):
    mode = "live"

    def __init__(self, source: str, cfg: IntegrationConfig, transport: httpx.BaseTransport | None = None):
        if not cfg.enabled:
            raise IntegrationDisabled(f"{source} integration is disabled")
        if not cfg.base_url:
            raise ValueError(f"{source}: base_url is required")
        self.source = source
        self.kpis = SOURCE_KPIS[source]
        self._cfg = cfg
        self._mapping = load_mapping(cfg.mapping_file)
        unknown = set(self._mapping) - set(self.kpis)
        if unknown:
            raise ValueError(f"{source}: mapping has KPIs this source does not supply: {sorted(unknown)}")
        self._http = httpx.Client(base_url=cfg.base_url, timeout=cfg.timeout_s,
                                  transport=transport or httpx.HTTPTransport(retries=2))
        self._token: tuple[str, float] | None = None
        # If a source says how its data was made (the mock systems send X-Data-Origin: ai|fallback), keep it
        # as lineage. A real vendor sends nothing, so real data is never marked.
        self._origins: dict[str, str] = {}

    def lineage_for(self, kpi: str) -> dict:
        return {"origin": self._origins[kpi]} if kpi in self._origins else {}

    @property
    def mapped_kpis(self) -> tuple[str, ...]:
        return tuple(k for k in self.kpis if k in self._mapping)

    def _auth_headers(self) -> dict[str, str]:
        c = self._cfg
        if c.auth == "bearer" and c.token:
            return {"Authorization": f"Bearer {c.token.get_secret_value()}"}
        if c.auth == "basic" and c.username and c.password:
            import base64

            raw = f"{c.username}:{c.password.get_secret_value()}".encode()
            return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
        if c.auth == "client_credentials" and c.token_url and c.client_id and c.client_secret:
            if self._token is None or self._token[1] < time.time() + 30:
                r = httpx.post(c.token_url, timeout=c.timeout_s, data={
                    "grant_type": "client_credentials", "client_id": c.client_id,
                    "client_secret": c.client_secret.get_secret_value()})
                r.raise_for_status()
                body = r.json()
                self._token = (body["access_token"], time.time() + float(body.get("expires_in", 300)))
            return {"Authorization": f"Bearer {self._token[0]}"}
        raise ValueError(f"{self.source}: credentials for auth={c.auth} are not configured")

    def fetch(self, company_code: str, period: str) -> dict[str, Raw]:
        year, month = period.split("-")
        ctx = {"company_code": company_code, "period": period, "year": year, "month": month}
        headers = {"Accept": "application/json", **self._auth_headers()}
        out: dict[str, Raw] = {}
        for kpi in self.mapped_kpis:
            m = self._mapping[kpi]
            params = {k: v.format_map(ctx) for k, v in m.get("params", {}).items()}
            resp = self._http.get(m["path"].format_map(ctx), params=params, headers=headers)
            resp.raise_for_status()
            origin = resp.headers.get("x-data-origin")
            if origin and origin != "none":
                self._origins[kpi] = origin
            else:
                self._origins.pop(kpi, None)
            row = dig(resp.json(), m.get("result_path", ""))
            if row is None:
                continue  # source has no row for this company/period -> no value
            raw: Raw = {}
            for field in SPECS[kpi].fields:
                api_name = m["fields"].get(field)
                val = row.get(api_name) if api_name else None
                raw[field] = None if val is None else float(val)
            out[kpi] = raw
        return out
