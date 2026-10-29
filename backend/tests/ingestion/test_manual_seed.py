import pytest
from sqlalchemy import select

from app.core.security import Role
from app.db.models import Company, KpiRecord, ManualInputHistory
from app.db.session import get_db
from app.ingestion.manual_seed import SEED_SOURCE, manual_inputs, seed_manual
from app.ingestion.stubgen import synthetic_company
from app.main import app
from tests.api.conftest import auth, client  # noqa: F401

MANUAL = {"cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"}
FY = [f"2026-{m:02d}" for m in range(4, 13)] + ["2027-01", "2027-02", "2027-03"]


@pytest.fixture()
def db(client):
    d = next(app.dependency_overrides[get_db]())
    yield d
    d.close()


def by_kpi(code, period):
    return {i.kpi_key: i for i in manual_inputs(synthetic_company(code), period)}


def test_all_four_manual_kpis_deterministic_and_plausible():
    a = by_kpi("IC010", "2026-10")
    assert set(a) == MANUAL
    assert by_kpi("IC010", "2026-10") == a
    codes = [f"IC{i:03d}" for i in range(1, 89)]
    gptw = [by_kpi(c, "2026-10")["gptw_score"].value for c in codes]
    assert all(0 <= g <= 100 for g in gptw) and max(gptw) - min(gptw) > 15  # varied around target 80
    cph = [i.recruitment_cost / i.hires for c in codes if (i := by_kpi(c, "2026-10")["cost_per_hire"]).hires]
    assert 30_000 < sorted(cph)[len(cph) // 2] < 120_000  # centred near the 60,000 target


@pytest.mark.parametrize("code", ["IC001", "IC002", "IC003", "IC004", "IC005", "IC006"])
def test_values_are_consistent_across_the_year(code):
    seq = [by_kpi(code, p) for p in FY]
    idps = [s["idps_top_talent"].value for s in seq]
    assert idps == sorted(idps) and idps[0] > 0            # year-to-date never decreases
    assert len({s["gptw_score"].value for s in seq}) == 1  # one annual survey, carried forward
    reviewed = [s["top_talent_review"].reviewed for s in seq]
    assert reviewed == sorted(reviewed)                    # once held, stays held
    dates = {s["top_talent_review"].review_date for s in seq if s["top_talent_review"].reviewed}
    assert len(dates) <= 1                                 # with one consistent date
    assert not any(reviewed[:4])  # nothing reviewed before August (April-July)


def test_seed_writes_flags_synthetic_and_is_idempotent(db, client):
    n = seed_manual(db, "2026-10")
    assert n == 3 * 4
    assert seed_manual(db, "2026-10") == n
    assert db.query(KpiRecord).count() == n
    assert {r.source for r in db.scalars(select(KpiRecord))} == {SEED_SOURCE}
    cph = db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "cost_per_hire"))
    assert cph.numerator is not None and cph.denominator is not None  # totals kept for group CPH
    sc = client.get("/scorecard", params={"period": "2026-10"}, headers=auth(Role.ADMIN)).json()
    assert sc["synthetic_data"] is True
    ic = sc["companies"][0]
    status = {k["key"]: k["excluded_reason"] for p in ic["pillars"] for k in p["kpis"]}
    assert status["gptw_score"] is None and status["idps_top_talent"] is None  # now scored, not "missing"
    assert status["top_talent_review"] == "not_due"  # still excluded before December


def test_seed_never_overwrites_a_real_entry_and_editor_save_replaces_seed(db, client):
    cid = db.scalar(select(Company.id).where(Company.code == "IC1"))
    editor = auth(Role.EDITOR)
    seed_manual(db, "2026-10")
    # an editor overwrites a seeded value -> becomes real, history shows the seeded value as "old"
    r = client.post("/inputs", json={"company_id": cid, "period": "2026-10", "kpi_key": "gptw_score",
                                     "value": 71.5}, headers=editor)
    assert r.status_code == 201
    rec = db.scalar(select(KpiRecord).where(KpiRecord.company_id == cid, KpiRecord.kpi_key == "gptw_score"))
    db.refresh(rec)
    assert rec.source == "manual" and rec.achievement == 71.5
    hist = db.scalars(select(ManualInputHistory)).all()
    assert len(hist) == 1 and hist[0].old_value["achievement"] != 71.5
    # re-seeding must not clobber the real value
    seed_manual(db, "2026-10")
    db.refresh(rec)
    assert rec.source == "manual" and rec.achievement == 71.5
