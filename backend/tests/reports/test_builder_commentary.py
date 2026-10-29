from types import SimpleNamespace as NS

import pytest

from app.reports import commentary
from app.reports.builder import build_report
from app.reports.integrity import canonical_hash
from app.reports.markdown import render_markdown


def kpi(key, reason=None, score=80.0):
    return {"key": key, "score": None if reason else score, "excluded_reason": reason}


def pillar(name, score, kpis=None):
    return {"pillar": name, "score": score, "eligible_weight": 1.0, "kpis": kpis or []}


def company(code, score, status, pillars=None, cov=1.0):
    return {"company_id": 1, "code": code, "name": code, "score": score, "status": status,
            "pillar_coverage": cov, "pillars": pillars or [pillar("a", score), pillar("b", score + 5 if score else None)]}


def card(group_score=82.0, status="amber", companies=None, synthetic=False, no_source=(), cov=1.0):
    return {"period": "x", "calc_version": "1", "scope": "group", "synthetic_data": synthetic,
            "no_source_kpis": list(no_source),
            "group": {"score": group_score, "status": status, "pillar_coverage": cov, "companies_in_scope": 3,
                      "companies_with_data": 3,
                      "pillars": [pillar("a", 90.0, [kpi("k1"), kpi("k2", "not_due")]), pillar("b", 70.0)]},
            "companies": companies or []}


LIN = {"sources": [{"source": "s", "label": "S", "mode": "stub", "kpis": [], "no_source_kpis": [],
                    "last_run": {"status": "success", "companies_ok": 3, "companies_failed": 0,
                                 "records_written": 9, "finished_at": None}}],
       "data_origin": {"stub": 9}}


def build(now, prev=None, lineage=LIN):
    return build_report("2026-10", "2026-09" if prev else None, now, prev, lineage, "tester", "2026-10-31T00:00:00")


def test_headline_comparison_movers_and_attention():
    now = card(82.0, "amber", [company("IC1", 50.0, "red"), company("IC2", 95.0, "green"), company("IC3", 80.0, "amber")])
    prev = card(85.0, "amber", [company("IC1", 92.0, "green"), company("IC2", 90.0, "green"), company("IC3", 60.0, "red")])
    r = build(now, prev)
    assert r["headline"]["group_score"] == 82 and r["headline"]["previous_group_score"] == 85
    assert r["headline"]["delta"] == -3.0
    assert [p["delta"] for p in r["headline"]["pillars"]] == [0.0, 0.0]
    assert [m["code"] for m in r["movers"]["improved"]] == ["IC3", "IC2"]     # biggest gain first
    assert [m["code"] for m in r["movers"]["declined"]] == ["IC1"]
    assert r["attention"]["newly_red"] == ["IC1"] and r["attention"]["red_count"] == 1
    assert r["attention"]["red"][0]["weakest_pillars"][0] == {"pillar": "a", "score": 50.0}
    assert r["headline"]["distribution"] == {"green": 1, "amber": 1, "red": 1, "none": 0}
    assert r["headline"]["previous_distribution"]["red"] == 1


def test_first_month_of_year_has_no_comparison_and_says_so():
    r = build(card(companies=[company("IC1", 80.0, "amber")]))
    assert r["headline"]["delta"] is None and r["movers"] == {"improved": [], "declined": []}
    assert any("first month" in c for c in r["caveats"])


def test_exceptions_separate_missing_from_no_source_and_not_due():
    cos = [company("IC1", 80.0, "amber", [pillar("a", 80.0, [kpi("k1", "missing"), kpi("k2")])]),
           company("IC2", 80.0, "amber", [pillar("a", 80.0, [kpi("k1", "missing")])], cov=0.5)]
    r = build(card(companies=cos, no_source=["k9"]))
    e = r["exceptions"]
    assert e["missing"] == [{"kpi": "k1", "missing_count": 2, "sample": ["IC1", "IC2"]}]
    assert e["no_source"] == ["k9"] and e["not_due"] == ["k2"]
    assert e["low_coverage"] == {"count": 1, "sample": ["IC2"]}


def test_caveats_cover_synthetic_coverage_and_failed_sources():
    bad = {"sources": [{**LIN["sources"][0], "last_run": {"status": "failed", "companies_ok": 0, "companies_failed": 3,
                                                          "records_written": 0, "finished_at": None}}], "data_origin": {}}
    r = build(card(synthetic=True, cov=0.45, companies=[company("IC1", 80.0, "amber")]), lineage=bad)
    text = " ".join(r["caveats"])
    assert "synthetic" in text and "45%" in text and "failed or partial" in text
    assert r["exceptions"]["ingestion_problems"] == [{"source": "s", "status": "failed", "failed": 3}]


def test_unscored_group_is_reported_not_crashed():
    r = build(card(group_score=None, status=None, companies=[company("IC1", None, None, [pillar("a", None)])]))
    assert r["headline"]["group_score"] is None and "No Group score" in commentary.template_commentary(commentary.build_facts(r))


def test_markdown_renders_all_sections():
    r = build(card(synthetic=True, companies=[company("IC1", 50.0, "red")]), card(companies=[company("IC1", 90.0, "green")]))
    r["commentary"] = {"text": "Hello.", "method": "template", "grounded": True, "issues": []}
    md = render_markdown(r)
    for needle in ("# Group HR Scorecard", "Synthetic data", "## Commentary", "## Pillars", "## Off track",
                   "## Exceptions", "## Sources and lineage", "## Caveats", "Calculation version 1"):
        assert needle in md


def test_canonical_hash_ignores_key_order_and_detects_change():
    a = {"x": 1, "y": [1, 2, {"b": 1, "a": 2}]}
    assert canonical_hash(a) == canonical_hash({"y": [1, 2, {"a": 2, "b": 1}], "x": 1})
    assert canonical_hash(a) != canonical_hash({**a, "x": 2})


# --- commentary grounding ---

@pytest.fixture()
def facts():
    r = build(card(82.4, "amber", [company("IC14", 50.3, "red"), company("IC2", 95.0, "green")]),
              card(85.1, "amber", [company("IC14", 92.0, "green"), company("IC2", 90.0, "green")]))
    return commentary.build_facts(r), r


@pytest.mark.parametrize("text,bad", [
    ("The Group score is 82.4, down 2.7 from 85.1.", []),
    ("About 82 overall, a fall of 2.7 points.", []),                       # rounding and sign are fine
    ("IC14 is at 50.3 and IC2 improved.", []),                             # company codes are not numbers
    ("In 2026-10 there are 7 pillars and 23 KPIs.", []),                   # periods and structure constants
    ("The Group score is 83.9.", ["83.9"]),                                # invented figure
    ("Scores fell 12 points.", ["12"]),                                    # invented delta
    ("1 company is red and 4 are amber.", ["4"]),                          # a count the engine never produced
])
def test_ungrounded_numbers(facts, text, bad):
    assert commentary.ungrounded_numbers(text, facts[0]) == bad


class FakeClient:
    def __init__(self, text=None, stop="end_turn", boom=None):
        self.calls, self.text, self.stop, self.boom = [], text, stop, boom
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise self.boom
        return NS(stop_reason=self.stop, content=[NS(type="text", text=self.text or "")])


def test_grounded_ai_text_is_used_and_prompt_is_safe(facts):
    _, report = facts
    c = FakeClient("The Group score is 82.4, down 2.7 from 85.1. IC14 is off track at 50.3.")
    out = commentary.generate(c, report)
    assert out["method"] == "ai" and out["grounded"] and out["issues"] == []
    call = c.calls[0]
    assert call["system"] == commentary.SYSTEM and "temperature" not in call
    assert "<facts>" in call["messages"][0]["content"] and "IC14" in call["messages"][0]["content"]


@pytest.mark.parametrize("client,issue", [
    (FakeClient("The Group score is 90.1."), "rejected_ungrounded_numbers:90.1"),
    (FakeClient(stop="refusal"), "llm_refusal"),
    (FakeClient(""), "llm_empty"),
    (FakeClient(boom=RuntimeError("secret key abc")), "llm_error:RuntimeError"),
    (None, "no_llm_configured"),
])
def test_anything_unusable_falls_back_to_the_template_without_failing(facts, client, issue):
    _, report = facts
    out = commentary.generate(client, report)
    assert out["method"] == "template" and out["issues"] == [issue]
    assert "82.4" in out["text"] and "secret" not in str(out)


def test_small_changes_never_render_as_negative_zero_and_precision_matches():
    now = card(82.04, "amber", [company("IC1", 80.0, "amber")])
    prev = card(82.06, "amber", [company("IC1", 80.0, "amber")])
    r = build(now, prev)
    assert r["headline"]["delta"] == 0.0 and str(r["headline"]["delta"]) == "0.0"
    r["commentary"] = {"text": "x", "method": "template", "grounded": True, "issues": []}
    assert "-0" not in render_markdown(r).replace("2026-10", "").replace("2026-09", "")
    now2 = card(82.3, "amber", [company("IC1", 80.0, "amber")])
    prev2 = card(82.0, "amber", [company("IC1", 80.0, "amber")])
    text = commentary.template_commentary(commentary.build_facts(build(now2, prev2)))
    assert "up 0.3 points from 82" in text and text.count("synthetic") == 0


def test_synthetic_warning_appears_once_in_the_template():
    r = build(card(synthetic=True, companies=[company("IC1", 80.0, "amber")]))
    assert commentary.template_commentary(commentary.build_facts(r)).lower().count("synthetic") == 1
