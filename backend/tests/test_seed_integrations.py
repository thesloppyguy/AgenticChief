from scripts.seed_integrations import fiscal_periods


def test_fiscal_periods_run_april_to_through_month():
    assert fiscal_periods("2026-10") == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert fiscal_periods("2026-04") == ["2026-04"]
    assert fiscal_periods("2027-02")[0] == "2026-04" and fiscal_periods("2027-02")[-1] == "2027-02"
    assert len(fiscal_periods("2027-03")) == 12
