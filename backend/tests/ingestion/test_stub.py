import json
from types import SimpleNamespace as NS

import anthropic
import pytest

from app.ingestion import ai_generator
from app.ingestion.raw import to_metric
from app.ingestion.stub import StubExtractor
from app.ingestion.stubgen import (
    CompanyBatch,
    CompanyRaw,
    assign_archetype,
    synthetic_company,
    to_kpi_raw,
    validate,
)


def test_synthetic_companies_are_valid_deterministic_and_varied():
    codes = [f"IC{i:03d}" for i in range(1, 89)]
    comps = [synthetic_company(c) for c in codes]
    assert all(validate(c) == [] for c in comps)
    assert synthetic_company("IC005") == synthetic_company("IC005")
    assert len({c.headcount for c in comps}) > 40
    assert {c.archetype for c in comps} == {"strong", "steady", "struggling", "early_stage"}


def test_archetype_assignment_distribution():
    arch = [assign_archetype(i, 88) for i in range(88)]
    share = {a: arch.count(a) / 88 for a in set(arch)}
    assert 0.15 < share["strong"] < 0.35 and 0.35 < share["steady"] < 0.55
    assert share["struggling"] > 0.1 and share["early_stage"] > 0.03


def test_stub_extractor_deterministic_jittered_and_valid():
    ex = StubExtractor("successfactors")
    a, b = ex.fetch("IC001", "2026-10"), ex.fetch("IC001", "2026-10")
    assert a == b
    assert ex.fetch("IC001", "2026-11") != a  # periods differ
    assert set(a) == set(ex.kpis)  # only its own KPIs
    for k, raw in a.items():
        to_metric(k, raw)  # never violates numerator <= denominator after jitter


def test_validate_catches_bad_ai_output():
    c = synthetic_company("IC001")
    bad = c.model_copy(update={"joined": c.offers + 5})
    assert any("offer_to_joining" in p for p in validate(bad))


class FakeMessages:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def parse(self, **kw):
        self.calls.append(kw)
        return self.behaviour(kw)


def _resp(parsed, stop="end_turn"):
    return NS(parsed_output=parsed, stop_reason=stop)


def test_generate_fixture_uses_ai_and_falls_back_per_company():
    def behaviour(kw):
        assert kw["output_format"] is CompanyBatch and "temperature" not in kw
        codes = [l.split(":")[0][2:] for l in kw["messages"][0]["content"].splitlines() if l.startswith("- ")]
        comps = []
        for code in codes:
            arch = next(l for l in kw["messages"][0]["content"].splitlines() if l.startswith(f"- {code}:")).split("=")[1]
            c = synthetic_company(code, arch)
            if code == "IC002":  # model returns an invalid record for one company
                c = c.model_copy(update={"retentions": c.avg_headcount + 10})
            comps.append(c)
        return _resp(CompanyBatch(companies=comps))

    client = NS(messages=FakeMessages(behaviour))
    fx = ai_generator.generate_fixture(client, "claude-opus-5-5", ["IC001", "IC002", "IC003"], batch_size=8)
    origins = {k: v["origin"] for k, v in fx["companies"].items()}
    assert origins == {"IC001": "ai", "IC002": "synthetic_fallback", "IC003": "ai"}
    assert fx["meta"]["ai_generated"] == 2 and len(client.messages.calls) == 1
    assert all(validate(CompanyRaw(**v["raw"])) == [] for v in fx["companies"].values())


@pytest.mark.parametrize("resp", [_resp(None, "refusal"), _resp(None, "max_tokens")])
def test_refusal_or_unparsed_batch_falls_back(resp):
    client = NS(messages=FakeMessages(lambda kw: resp))
    fx = ai_generator.generate_fixture(client, "m", ["IC001", "IC002"])
    assert {v["origin"] for v in fx["companies"].values()} == {"synthetic_fallback"}
    assert fx["meta"]["notes"]


def test_api_error_falls_back_and_is_noted():
    def boom(kw):
        raise anthropic.APIConnectionError(request=NS())
    fx = ai_generator.generate_fixture(NS(messages=FakeMessages(boom)), "m", ["IC001"])
    assert fx["companies"]["IC001"]["origin"] == "synthetic_fallback"
    assert "connection_error" in fx["meta"]["notes"][0]


def test_fixture_roundtrip_feeds_stub_extractor(tmp_path):
    fx = {"meta": {}, "companies": {"IC001": {"origin": "ai", "raw": synthetic_company("IC001").model_dump()}}}
    p = tmp_path / "fx.json"
    ai_generator.write_fixture(p, fx)
    loaded = ai_generator.load_fixture(p)
    assert ai_generator.load_fixture(tmp_path / "missing.json") is None
    base = to_kpi_raw(loaded["IC001"])["kra_submission"]
    got = StubExtractor("successfactors", loaded).fetch("IC001", "2026-10")["kra_submission"]
    assert got["eligible"] == base["eligible"] and abs(got["submitted"] - base["submitted"]) <= base["submitted"] * 0.04 + 1
    json.loads(p.read_text())


def test_deterministic_fixture_is_valid_and_loadable(tmp_path):
    codes = [f"IC{i:03d}" for i in range(1, 89)]
    fx = ai_generator.deterministic_fixture(codes)
    assert fx["meta"]["ai_generated"] == 0 and len(fx["companies"]) == 88
    assert {v["origin"] for v in fx["companies"].values()} == {"deterministic"}
    p = tmp_path / "f.json"
    ai_generator.write_fixture(p, fx)
    loaded = ai_generator.load_fixture(p)
    assert len(loaded) == 88 and all(validate(c) == [] for c in loaded.values())


def test_training_calendar_never_exceeds_one_before_october():
    ex = StubExtractor("successfactors")
    for code in (f"IC{i:03d}" for i in range(1, 60)):
        for p in ("2026-04", "2026-07", "2026-09"):
            assert ex.fetch(code, p)["training_calendar"]["value"] <= 1
    assert any(ex.fetch(f"IC{i:03d}", "2026-10")["training_calendar"]["value"] == 2 for i in range(1, 60))
