"""The shape of each mock source system's API: one definition drives BOTH the endpoints this app serves and
the mapping files the live adapters read, so the two cannot drift apart.

Each source deliberately has its own style (OData, plain REST, flat, nested), like real systems do.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.ingestion.raw import SPECS
from app.ingestion.sources import SOURCE_KPIS


def pascal(s: str) -> str:
    return "".join(p.capitalize() for p in s.split("_"))


def camel(s: str) -> str:
    p = pascal(s)
    return p[:1].lower() + p[1:]


@dataclass(frozen=True)
class Style:
    source: str
    path: Callable[[str], str]  # kpi -> path below /mock-sources/<source>
    params: dict[str, str]  # query template, with {company_code} and {period}
    parse: Callable[[dict[str, str]], tuple[str, str]]  # query -> (company_code, period)
    wrap: Callable[[dict | None], dict]  # row (or None for "no row") -> response body
    result_path: str  # where the row sits in the body
    field: Callable[[str], str]  # raw field name -> API field name


_FILTER = re.compile(r"companyCode eq '([^']+)' and period eq '([^']+)'")


def _odata(q: dict[str, str]) -> tuple[str, str]:
    m = _FILTER.fullmatch(q.get("$filter", ""))
    if not m:
        raise ValueError("$filter must be: companyCode eq '<code>' and period eq '<YYYY-MM>'")
    return m.group(1), m.group(2)


def _query(company: str, period: str) -> Callable[[dict[str, str]], tuple[str, str]]:
    def parse(q: dict[str, str]) -> tuple[str, str]:
        if company not in q or period not in q:
            raise ValueError(f"query parameters {company} and {period} are required")
        return q[company], q[period]
    return parse


STYLES: dict[str, Style] = {s.source: s for s in (
    Style("successfactors", lambda k: f"/odata/v2/{pascal(k)}",
          {"$filter": "companyCode eq '{company_code}' and period eq '{period}'", "$format": "json"}, _odata,
          lambda row: {"d": {"results": [row] if row else []}}, "d.results.0", pascal),
    Style("peoplestrong", lambda k: f"/api/v1/recruitment/{k.replace('_', '-')}",
          {"company": "{company_code}", "period": "{period}"}, _query("company", "period"),
          lambda row: {"status": "ok", "data": row}, "data", lambda f: f),
    Style("myhealth", lambda k: "/v2/ahc/summary",
          {"orgCode": "{company_code}", "month": "{period}"}, _query("orgCode", "month"),
          lambda row: row if row else {}, "", camel),
    Style("hi5plus", lambda k: "/engagement/adoption",
          {"entity": "{company_code}", "ym": "{period}"}, _query("entity", "ym"),
          lambda row: {"result": {"adoption": row}}, "result.adoption", camel),
)}


def prefix(source: str) -> str:
    return f"/mock-sources/{source}"


def mapping_for(source: str) -> dict:
    """The live adapter's mapping file for this source: where each KPI's raw counts come from."""
    st = STYLES[source]
    return {kpi: {"path": prefix(source) + st.path(kpi), "params": dict(st.params), "result_path": st.result_path,
                  "fields": {raw: st.field(raw) for raw in SPECS[kpi].fields}}
            for kpi in SOURCE_KPIS[source]}
