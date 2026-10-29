from dataclasses import replace

import pytest

from app.kpi_registry.seed import DEFAULT_CONFIG as CFG
from app.kpi_registry.seed import KPIS
from app.scoring import score_group, score_ic, score_value, status_for
from app.scoring.models import Direction, KpiValue, MissingICPolicy, Status


def v(x, **kw):
    return KpiValue(x, **kw)


def test_seed_shape():
    assert len(KPIS) == 23
    assert sum(CFG.pillar_weights.values()) == pytest.approx(1.0)
    for p in CFG.pillar_weights:
        assert sum(k.weight for k in KPIS if k.pillar == p) == pytest.approx(1.0)


def test_higher_and_lower_scoring():
    assert score_value(80, 100, Direction.HIGHER, CFG) == 80
    assert score_value(120, 60, Direction.LOWER, CFG) == 50
    assert score_value(120, 100, Direction.HIGHER, CFG) == 120  # uncapped by default
    assert score_value(120, 100, Direction.HIGHER, replace(CFG, score_cap=100)) == 100
    assert score_value(0, 60, Direction.LOWER, CFG) == CFG.zero_lower_is_better_score


def test_status_bands_use_unrounded_score():
    assert status_for(89.99, CFG) is Status.AMBER
    assert status_for(90, CFG) is Status.GREEN
    assert status_for(74.99, CFG) is Status.RED
    assert status_for(75, CFG) is Status.AMBER
    assert status_for(None, CFG) is None


def test_not_due_and_missing_rescale_pillar():
    vals = {"kra_submission": v(50), "ppw_on_time": v(1), "continuous_feedback": v(2)}
    # May: KRA (from June) and mid-term (from Dec) not due; feedback+ppw score 100.
    r = score_ic(KPIS, vals, month=5, cfg=CFG)
    pm = next(p for p in r.pillars if p.pillar == "performance_management")
    assert pm.score == pytest.approx(100)
    assert pm.eligible_weight == pytest.approx(0.5)
    # June: KRA now due at 50% -> (100+50+100)/3
    pm6 = next(p for p in score_ic(KPIS, vals, 6, CFG).pillars
               if p.pillar == "performance_management")
    assert pm6.score == pytest.approx(250 / 3)


def test_training_calendar_target_steps():
    vals = {"training_calendar": v(1)}
    def s(month):
        r = score_ic(KPIS, vals, month, CFG)
        lnd = next(p for p in r.pillars if p.pillar == "learning_development")
        return lnd.score
    assert s(4) == 100   # target 1 from April
    assert s(10) == 50   # target 2 from October
    assert s(2) == 50    # Feb is still in the Oct-Mar half


def test_empty_pillar_excluded_and_coverage_reported():
    r = score_ic(KPIS, {"overall_retention": v(100)}, 8, CFG)
    assert r.score == pytest.approx(100)
    assert r.pillar_coverage == pytest.approx(0.15)
    empty = score_ic(KPIS, {}, 8, CFG)
    assert empty.score is None and empty.status is None


def test_group_cost_per_hire_uses_totals_not_average_of_ratios():
    ics = {
        "a": {"cost_per_hire": v(100000, numerator=100000, denominator=1)},
        "b": {"cost_per_hire": v(50000, numerator=5_000_000, denominator=100)},
    }
    from app.scoring import group_values
    g = group_values(KPIS, ics, CFG)["cost_per_hire"]
    assert g.achievement == pytest.approx(5_100_000 / 101)  # not 75,000


def test_group_average_and_missing_ic_policy():
    ics = {"a": {"overall_retention": v(100)}, "b": {"overall_retention": v(50)},
           "c": {}}
    from app.scoring import group_values
    assert group_values(KPIS, ics, CFG)["overall_retention"].achievement == 75
    zero = replace(CFG, missing_ic_policy=MissingICPolicy.ZERO)
    assert group_values(KPIS, ics, zero)["overall_retention"].achievement == 50
    assert score_group(KPIS, ics, 8, CFG).score == pytest.approx(75)


def test_no_source_is_excluded_rescaled_and_distinct_from_missing():
    ns = replace(CFG, no_source=frozenset({"time_to_fill", "cost_per_hire"}))
    vals = {"offer_to_joining": v(50), "time_to_fill": v(30),  # a stale value must be ignored
            "new_hire_retention_12m": v(100)}
    r = score_ic(KPIS, vals, 8, ns)
    ta = next(p for p in r.pillars if p.pillar == "talent_acquisition")
    reasons = {k.key: k.excluded_reason for k in ta.kpis}
    assert reasons == {"offer_to_joining": None, "time_to_fill": "no_source",
                       "new_hire_retention_12m": None, "cost_per_hire": "no_source"}
    assert ta.score == pytest.approx(75)            # (50 + 100) / 2: rescaled over eligible KPIs
    assert ta.eligible_weight == pytest.approx(0.5)
    # a KPI that is merely missing keeps the "missing" reason
    plain = score_ic(KPIS, {"offer_to_joining": v(50)}, 8, CFG)
    assert {k.key: k.excluded_reason for p in plain.pillars for k in p.kpis}["time_to_fill"] == "missing"


def test_not_due_takes_precedence_and_whole_pillar_no_source_is_unscored():
    ns = replace(CFG, no_source=frozenset({"kra_submission"}))
    r = score_ic(KPIS, {}, 5, ns)  # May: KRA not due yet
    pm = next(p for p in r.pillars if p.pillar == "performance_management")
    assert {k.key: k.excluded_reason for k in pm.kpis}["kra_submission"] == "not_due"
    allns = replace(CFG, no_source=frozenset(k.key for k in KPIS if k.pillar == "retention"))
    res = score_ic(KPIS, {k.key: v(100) for k in KPIS}, 8, allns)
    assert next(p for p in res.pillars if p.pillar == "retention").score is None
    assert res.pillar_coverage == pytest.approx(0.85)  # coverage reports the lost pillar weight


def test_group_no_source():
    ns = replace(CFG, no_source=frozenset({"overall_retention"}))
    ics = {"a": {"overall_retention": v(100)}, "b": {"overall_retention": v(50)}}
    g = score_group(KPIS, ics, 8, ns)
    ret = next(p for p in g.pillars if p.pillar == "retention")
    assert {k.key: k.excluded_reason for k in ret.kpis}["overall_retention"] == "no_source"
