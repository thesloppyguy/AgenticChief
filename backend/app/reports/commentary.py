"""Leadership commentary. The model may phrase the facts but must not introduce numbers.

AI text is accepted only if every number in it appears in the computed facts; otherwise a deterministic
template built from the same facts is used instead. So a published commentary never says something the
scoring engine did not compute.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import settings
from app.kpi_registry.seed import PILLAR_LABELS

SYSTEM = """You write the commentary section of a monthly Group HR scorecard review for senior leadership.
You are given FACTS as JSON, produced by a deterministic scoring engine.

Rules:
- Use ONLY numbers that appear in FACTS. Never calculate, sum, count, average or estimate anything yourself.
  If a figure you want is not in FACTS, describe it in words without a number.
- Write three short paragraphs, under 180 words in total: (1) the headline and how it moved, (2) what needs
  attention, (3) data quality and caveats.
- Always state the coverage caveats listed in FACTS, and say clearly if the data is synthetic.
- Never describe a KPI with no source as a company's failure. It is a connection gap.
- Plain prose, no headings, bullets or markdown. Refer to companies by their codes."""

_WHITELIST = {7.0, 23.0}  # 7 pillars, 23 sub-KPIs: structural constants, not results
_CODE = re.compile(r"\bIC\d+\b")
_DATE = re.compile(r"\b\d{4}-\d{2}\b|\b20\d\d\b")
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def build_facts(report: dict) -> dict:
    """The only information the commentary may rely on."""
    h = report["headline"]
    return {
        "period": report["meta"]["period"],
        "group": {"score": h["group_score"], "status": h["group_status"], "previous": h["previous_group_score"],
                  "change": h["delta"], "coverage_pct": h["coverage_pct"],
                  "companies_with_data": report["meta"]["companies_with_data"],
                  "companies_in_scope": report["meta"]["companies_in_scope"]},
        "pillars": [{"pillar": p["pillar"], "score": p["score"], "status": p["status"], "change": p["delta"]}
                    for p in h["pillars"]],
        "companies_by_status": h["distribution"],
        "most_improved": [{"code": m["code"], "change": m["delta"]} for m in report["movers"]["improved"][:3]],
        "most_declined": [{"code": m["code"], "change": m["delta"]} for m in report["movers"]["declined"][:3]],
        "red_companies": {"count": report["attention"]["red_count"],
                          "lowest": [{"code": r["code"], "score": r["score"]} for r in report["attention"]["red"][:5]],
                          "newly_red": report["attention"]["newly_red"][:10]},
        "kpis_with_no_source": len(report["exceptions"]["no_source"]),
        "caveats": report["caveats"],
        "synthetic_data": report["meta"]["synthetic_data"],
    }


def _leaves(x: Any) -> list[float]:
    if isinstance(x, bool):
        return []
    if isinstance(x, (int, float)):
        return [float(x)]
    if isinstance(x, dict):
        return [n for v in x.values() for n in _leaves(v)]
    if isinstance(x, list):
        return [n for v in x for n in _leaves(v)]
    if isinstance(x, str):  # numbers inside caveat sentences count as stated facts
        return [float(t) for t in _NUM.findall(_CODE.sub("", _DATE.sub("", x)))]
    return []


def ungrounded_numbers(text: str, facts: dict) -> list[str]:
    """Numbers in `text` that cannot be traced to `facts` (allowing for rounding and sign)."""
    allowed = set(_leaves(facts)) | _WHITELIST
    allowed |= {abs(a) for a in allowed}
    bad = []
    for tok in _NUM.findall(_CODE.sub("", _DATE.sub("", text))):
        decimals = len(tok.split(".")[1]) if "." in tok else 0
        v = abs(float(tok))
        if not any(round(a, decimals) == v for a in allowed):
            bad.append(tok)
    return bad


def _label(key: str) -> str:
    return PILLAR_LABELS.get(key) or key.replace("_", " ")


def template_commentary(facts: dict) -> str:
    g = facts["group"]
    parts = []
    if g["score"] is None:
        parts.append(f"No Group score could be computed for {facts['period']} because no scoreable data is available.")
    else:
        move = ""
        if g["change"] is not None:
            move = (f", {'up' if g['change'] > 0 else 'down' if g['change'] < 0 else 'unchanged'}"
                    + (f" {abs(g['change'])} points from {g['previous']}" if g["change"] else f" from {g['previous']}"))
        parts.append(f"The Group HR score for {facts['period']} is {g['score']} ({g['status']}){move}.")
        dist = facts["companies_by_status"]
        parts[-1] += f" {dist['green']} companies are on track, {dist['amber']} need attention and {dist['red']} are off track."
    scored = [p for p in facts["pillars"] if p["score"] is not None]
    if scored:
        weakest = min(scored, key=lambda p: p["score"])
        parts.append(f"The weakest pillar is {_label(weakest['pillar'])} at {weakest['score']}.")
    red = facts["red_companies"]
    if red["count"]:
        low = ", ".join(f"{r['code']} ({r['score']})" for r in red["lowest"][:3])
        parts.append(f"{red['count']} companies are off track; the lowest are {low}.")
    parts.extend(facts["caveats"])  # includes the synthetic-data warning when it applies
    return " ".join(parts)


def generate(client: Any | None, report: dict) -> dict:
    """Returns {text, method: 'ai'|'template', grounded, issues}. Never raises."""
    facts = build_facts(report)
    fallback = {"text": template_commentary(facts), "method": "template", "grounded": True, "issues": []}
    if client is None:
        return {**fallback, "issues": ["no_llm_configured"]}
    try:
        resp = client.messages.create(
            model=settings.default_model, max_tokens=2000, system=SYSTEM,
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": "<facts>\n" + json.dumps(facts, sort_keys=True) + "\n</facts>"}],
        )
    except Exception as e:  # noqa: BLE001 - commentary must never fail the whole report
        return {**fallback, "issues": [f"llm_error:{type(e).__name__}"]}
    if getattr(resp, "stop_reason", None) == "refusal":
        return {**fallback, "issues": ["llm_refusal"]}
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if not text:
        return {**fallback, "issues": ["llm_empty"]}
    bad = ungrounded_numbers(text, facts)
    if bad:  # reject the whole draft rather than publish a figure nobody computed
        return {**fallback, "issues": [f"rejected_ungrounded_numbers:{','.join(bad[:5])}"]}
    return {"text": text, "method": "ai", "grounded": True, "issues": []}
