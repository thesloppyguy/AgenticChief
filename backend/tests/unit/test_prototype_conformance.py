"""The Group HR Scorecard prototype (assets/image.png) is the source of truth for the rules. This pins every
row of it, transcribed by hand, against the configuration the engine actually uses.

It cannot check COMPUTED results: the image is the blank template (Achievement and Score are empty). When the
Excel workbook with sample data is available, add a test that loads it and compares pillar, company, Group and
status results exactly. Until then this guarantees the configuration cannot drift from the prototype.
"""
import pytest

from app.ingestion.sources import SOURCE_KPIS, SOURCE_LABELS
from app.knowledge.builtin import FORMULAS
from app.kpi_registry.seed import KPIS, PILLAR_LABELS, PILLAR_WEIGHTS
from app.scoring.models import Direction
from app.services.manual_inputs import MANUAL_KPIS

# (pillar objective as printed, pillar weight, [(our key, as printed: measure of success, weight, unit, target, system, formula phrases)])
SHEET = [
    ("Talent Acquisition", 0.15, [
        ("offer_to_joining", "Offer-to-Joining Ratio", 0.25, "%", 100, "PeopleStrong/Skima AI/SuccessFactors", ["joined", "offers released"]),
        ("time_to_fill", "Time to Fill", 0.25, "Days", 60, "PeopleStrong/Skima AI/SuccessFactors", ["offer acceptance", "requisition approv", "positions closed"]),
        ("new_hire_retention_12m", "12-Month New Hire Retention", 0.25, "%", 100, "PeopleStrong/Skima AI/SuccessFactors", ["12 months", "same cohort"]),
        ("cost_per_hire", "Cost per Hire", 0.25, "₹ / hire", 60000, "PeopleStrong/Skima AI/SuccessFactors", ["recruitment cost", "total hires"]),
    ]),
    ("Performance Management", 0.15, [
        ("ppw_on_time", "Organising PPW within timelines", 0.25, "1/0", 1, "SuccessFactors", ["Planning Workshop", "1 April"]),
        ("kra_submission", "KRA Submission Timeliness", 0.25, "%", 100, "SuccessFactors", ["submitted", "30 June", "eligible"]),
        ("mid_term_review", "Mid-Term Review Timeliness", 0.25, "%", 100, "SuccessFactors", ["Mid-Term Review", "31 December", "eligible"]),
        ("continuous_feedback", "Continous Feedback", 0.25, "%", 2, "SuccessFactors", ["two feedback", "mid-term review"]),
    ]),
    ("Learning & Development", 0.15, [
        ("tni_employees", "TNI for Employees", 0.25, "%", 100, "SuccessFactors", ["Training Needs Identification", "eligible"]),
        ("training_calendar", "Half Yearly Training Calendar within timelines", 0.25, "2,1,0", 2, "SuccessFactors", ["calendar", "1 from April", "2 from October"]),
        ("tni_fulfilment", "TNI Fulfilment Rate", 0.25, "%", 100, "SuccessFactors", ["fulfilled", "identified"]),
        ("l1_feedback", "Level 1 Feedback on Training Programs", 0.25, "%", 80, "SuccessFactors", ["Level 1", "1 to 5"]),
    ]),
    ("Organizational Effectiveness", 0.10, [
        ("role_skill_coverage", "Percentage of employees covered", 1.00, "%", 100, "SuccessFactors", ["skills and proficiency", "role"]),
    ]),
    ("Talent Management", 0.20, [
        ("top_talent_review", "Talent Council - Top Talent Review", 0.25, "1 or 0", 1, "Talent Review", ["31 December"]),
        ("idps_top_talent", "IDPs Created for Top Talent", 0.25, "%", 25, "Talent Review", ["Individual Development Plans", "top talent"]),
        ("pli_assessment", "PLI Assessment", 0.25, "%", 100, "SuccessFactors", ["M3C and M4A", "PLI report"]),
        ("idp_creation_rate", "IDP Creation Rate for Target Employees", 0.25, "%", 100, "SuccessFactors", ["Target employees", "IDP"]),
    ]),
    ("Engagement / Wellness", 0.10, [
        ("ahc_completion", "Annual Health Check-up (AHC) Completion Rate", 0.25, "%", 100, "MyHealth", ["Annual Health Check-up", "eligible"]),
        ("platform_adoption", "Platform Adoption Rate", 0.25, "%", 80, "Hi5Plus / HeeraPlus", ["logged in", "active employees"]),
        ("gptw_score", "GPTW Survey Score", 0.50, "Score", 80, "GPTW Score", ["Trust Index", "survey report"]),
    ]),
    ("Retention", 0.15, [
        ("overall_retention", "Overall Retention Rate", 0.30, "%", 100, "SuccessFactors", ["retentions", "average headcount"]),
        ("top_talent_retention", "Top Talent Retention Rate", 0.40, "%", 100, "SuccessFactors", ["regrettable exits", "CPR 7"]),
        ("trainee_retention", "Trainee Retention", 0.30, "%", 80, "SuccessFactors", ["Trainees remaining", "onboarded"]),
    ]),
]
ROWS = [(pw, pillar, *row) for pillar, pw, rows in SHEET for row in rows]
BY_KEY = {k.key: k for k in KPIS}
LOWER_IS_BETTER = {"time_to_fill", "cost_per_hire"}                      # the sheet's formulas: "lower is better"


def test_the_sheet_has_23_rows_in_7_pillars_and_everything_adds_up():
    assert len(ROWS) == 23 and len(SHEET) == 7
    assert sum(p for _, p, _ in SHEET) == pytest.approx(1.0)                                      # the 100.00% in the sheet's corner
    for pillar, _, rows in SHEET:
        assert sum(r[2] for r in rows) == pytest.approx(1.0), pillar                              # each pillar's block totals 100%


def test_pillar_names_order_and_weights_match_the_sheet():
    assert [PILLAR_LABELS[p] for p in PILLAR_WEIGHTS] == [p for p, _, _ in SHEET]                 # the sheet's own names and order
    for pillar, weight, _ in SHEET:
        key = next(k for k, v in PILLAR_LABELS.items() if v == pillar)
        assert PILLAR_WEIGHTS[key] == pytest.approx(weight), pillar


def test_we_have_exactly_the_sheets_kpis_and_nothing_else():
    assert set(BY_KEY) == {r[2] for r in ROWS} and len(KPIS) == 23


@pytest.mark.parametrize("row", ROWS, ids=[r[3] for r in ROWS])
def test_each_row_matches_the_sheet(row):
    _pweight, pillar, key, printed, weight, unit, target, _system, phrases = row
    k = BY_KEY[key]
    assert PILLAR_LABELS[k.pillar] == pillar
    assert k.weight == pytest.approx(weight), f"{printed}: weight in pillar"
    # The sheet prints the year-end target. A KPI with a calendar rule reaches it in its last step.
    final = k.target_steps[-1][1] if k.target_steps else k.target
    assert final == target, f"{printed}: target ({unit})"
    assert k.direction is (Direction.LOWER if key in LOWER_IS_BETTER else Direction.HIGHER), f"{printed}: direction"
    text = FORMULAS[key].lower()
    for ph in phrases:
        assert ph.lower() in text, f"{printed}: the formula should mention '{ph}'"


def test_training_calendar_follows_the_sheets_april_october_rule():
    k = BY_KEY["training_calendar"]
    assert k.target == 1 and dict(k.target_steps) == {4: 1, 10: 2}                                 # the sheet shows 2; the rule: 1 from April, 2 from October


def test_due_months_match_the_sheet():
    assert BY_KEY["kra_submission"].due_from_month == 6                                           # "on or before 30th June"
    assert BY_KEY["mid_term_review"].due_from_month == 12 and BY_KEY["top_talent_review"].due_from_month == 12   # "31st Dec"
    assert {k.key for k in KPIS if k.due_from_month} == {"kra_submission", "mid_term_review", "top_talent_review"}


def test_systems_match_the_sheet_and_exactly_the_four_manual_kpis_are_entered_by_hand():
    source_of = {k: SOURCE_LABELS[s] for s, ks in SOURCE_KPIS.items() for k in ks}
    for _, _, key, printed, _, _, _, system, _ in ROWS:
        if key in MANUAL_KPIS:
            continue
        if system == "SuccessFactors":
            assert source_of[key] == "SAP SuccessFactors", printed
        elif system == "MyHealth":
            assert source_of[key] == "MyHealth", printed
        elif system == "Hi5Plus / HeeraPlus":
            assert source_of[key] == "Hi5Plus / HeeraPlus", printed
        else:
            # The sheet lists three systems for Talent Acquisition. ASSUMPTION (see app/ingestion/sources.py): PeopleStrong.
            assert system == "PeopleStrong/Skima AI/SuccessFactors" and "PeopleStrong" in source_of[key], printed
    assert MANUAL_KPIS == {"cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"}  # the four the brief names
    assert len(source_of) == 19                                                                    # "data sources (19 sub-KPIs)"
