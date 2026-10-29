import pytest

from app.ingestion.raw import SPECS, RawDataError, to_metric
from app.ingestion.sources import SOURCE_KPIS
from app.kpi_registry.seed import KPIS
from app.services.manual_inputs import MANUAL_KPIS


def test_sources_cover_exactly_the_19_sourced_kpis():
    all_src = [k for ks in SOURCE_KPIS.values() for k in ks]
    assert len(all_src) == len(set(all_src)) == 19  # no KPI claimed twice
    assert set(all_src) == {k.key for k in KPIS} - MANUAL_KPIS
    assert set(all_src) == set(SPECS)


def test_ratio_value_and_edge_cases():
    m = to_metric("kra_submission", {"submitted": 90, "eligible": 120})
    assert m.achievement == pytest.approx(75) and (m.numerator, m.denominator) == (90, 120)
    assert to_metric("kra_submission", {"submitted": 0, "eligible": 0}).achievement is None  # no population
    assert to_metric("kra_submission", {"submitted": None, "eligible": 10}).achievement is None
    with pytest.raises(RawDataError):
        to_metric("kra_submission", {"submitted": 11, "eligible": 10})
    with pytest.raises(RawDataError):
        to_metric("kra_submission", {"submitted": -1, "eligible": 10})


def test_top_talent_retention_formula():
    m = to_metric("top_talent_retention", {"regrettable_exits": 3, "avg_headcount_cpr7": 60})
    assert m.achievement == pytest.approx(95.0)


def test_value_kinds():
    assert to_metric("l1_feedback", {"avg_rating_5": 4.0}).achievement == pytest.approx(80)
    with pytest.raises(RawDataError):
        to_metric("l1_feedback", {"avg_rating_5": 6})
    assert to_metric("time_to_fill", {"avg_days": 55, "positions_closed": 0}).achievement is None
    assert to_metric("time_to_fill", {"avg_days": 55, "positions_closed": 4}).achievement == 55
    with pytest.raises(RawDataError):
        to_metric("training_calendar", {"value": 3})
    with pytest.raises(RawDataError):
        to_metric("cost_per_hire", {"x": 1})  # manual KPI is not a sourced KPI
