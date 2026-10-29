from __future__ import annotations

from app.kpi_registry.seed import PILLAR_LABELS


def _n(x, d=1) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        x = round(x, d) + 0.0  # never print "-0"
        return f"{x:.{d}f}".rstrip("0").rstrip(".")
    return str(x)


def _pillar(p: str) -> str:
    return PILLAR_LABELS.get(p) or p.replace("_", " ").title()


def render_markdown(r: dict) -> str:
    m, h = r["meta"], r["headline"]
    out = [f"# Group HR Scorecard: monthly review, {m['period']}", ""]
    if m["synthetic_data"]:
        out += ["> **Synthetic data.** Not suitable for decisions.", ""]
    move = "" if h["delta"] is None else f" ({'+' if h['delta'] > 0 else ''}{_n(h['delta'])} vs {m['previous_period']})"
    out += [(f"**Group score: {_n(h['group_score'])}** ({h['group_status'] or 'no data'}){move}. "
            f"Based on {h['coverage_pct']}% of scorecard weight; {m['companies_with_data']} of "
            f"{m['companies_in_scope']} companies have data."), ""]
    c = r.get("commentary")
    if c:
        out += ["## Commentary", "", c["text"], "",
                f"*{'AI-drafted; every number verified against computed results' if c['method'] == 'ai' else 'Template (generated from computed results)'}.*", ""]
    out += ["## Pillars", "", "| Pillar | Score | Status | Previous | Change |", "|---|---|---|---|---|"]
    out += [f"| {_pillar(p['pillar'])} | {_n(p['score'])} | {p['status'] or '—'} | {_n(p['previous'])} | {_n(p['delta'])} |"
            for p in h["pillars"]]
    d = h["distribution"]
    out += ["", f"Companies: {d['green']} on track, {d['amber']} need attention, {d['red']} off track, {d['none']} no data.", ""]
    a = r["attention"]
    if a["red"]:
        out += [f"## Off track ({a['red_count']})", ""]
        out += [f"- {x['code']}: {_n(x['score'])}; weakest: " + ", ".join(f"{_pillar(w['pillar'])} {_n(w['score'])}" for w in x["weakest_pillars"])
                for x in a["red"]]
        out += [""]
    mv = r["movers"]
    for title, rows in (("Most improved", mv["improved"]), ("Most declined", mv["declined"])):
        if rows:
            out += [f"## {title}", ""] + [f"- {x['code']}: {_n(x['previous'])} to {_n(x['score'])} ({_n(x['delta'])})" for x in rows] + [""]
    e = r["exceptions"]
    out += ["## Exceptions", ""]
    if e["no_source"]:
        out += [f"- **No source ({len(e['no_source'])} KPIs):** " + ", ".join(k.replace("_", " ") for k in e["no_source"])]
    for x in e["missing"][:10]:
        out += [f"- Missing: {x['kpi'].replace('_', ' ')} for {x['missing_count']} companies (e.g. {', '.join(x['sample'][:5])})"]
    if e["not_due"]:
        out += ["- Not yet due: " + ", ".join(k.replace("_", " ") for k in e["not_due"])]
    if e["low_coverage"]["count"]:
        out += [f"- {e['low_coverage']['count']} companies have at least one pillar with nothing scoreable"]
    out += [""]
    out += ["## Sources and lineage", "", "| Source | Mode | Last run | OK / failed |", "|---|---|---|---|"]
    for s in r["lineage"]["sources"]:
        lr = s["last_run"]
        out += [(f"| {s['label']} | {s['mode']} | {lr['status'] if lr else 'never'} | "
                f"{lr['companies_ok'] if lr else '—'} / {lr['companies_failed'] if lr else '—'} |")]
    origin = r["lineage"]["data_origin"]
    out += ["", "Data origin (records this period): " + ", ".join(f"{k} {v}" for k, v in sorted(origin.items())), ""]
    if r["caveats"]:
        out += ["## Caveats", ""] + [f"- {c}" for c in r["caveats"]] + [""]
    out += ["---", f"Calculation version {m['calc_version']} · generated {m['generated_at']} by {m['generated_by']}"]
    return "\n".join(out)
