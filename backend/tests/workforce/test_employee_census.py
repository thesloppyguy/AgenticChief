"""Employee census simulation, aggregation, metrics, and reset wipe."""
from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import (
    Employee,
    EmployeeEvent,
    EmployeePerformance,
    MockCompanyData,
)
from app.db.session import SessionLocal
from app.ingestion.stubgen import validate
from app.org.reset import reset_org
from app.workforce.employee_sim.aggregate import to_company_raw
from app.workforce.employee_sim.generate import simulate_group, simulate_ic
from app.workforce.employee_sim.persist import persist_batch, seed_census
from app.workforce.metrics import compute_metrics


def test_simulate_ic_demo_scale_and_stable():
    a = simulate_ic("LTIM", "strong", seed="test-v1")
    b = simulate_ic("LTIM", "strong", seed="test-v1")
    assert a.model_dump() == b.model_dump()
    active = [e for e in a.employees if e.status == "active"]
    assert 80 <= len(active) <= 150
    assert any(e.manager_ps_number for e in active)
    assert any(e.is_trainee for e in active)
    assert any(e.events for e in a.employees)


def test_to_company_raw_passes_validate():
    batch = simulate_ic("LTTS", "strong", n=100, seed="agg-v1")
    raw = to_company_raw(batch)
    problems = validate(raw)
    assert problems == [], problems
    assert raw.headcount == sum(1 for e in batch.employees if e.status == "active")
    assert raw.company_code == "LTTS"
    assert raw.archetype == "strong"


def test_archetype_quality_separation():
    strong = to_company_raw(simulate_ic("LTTS", "strong", n=110, seed="arch-s"))
    struggling = to_company_raw(simulate_ic("LTMR", "struggling", n=110, seed="arch-w"))
    # Strong should generally show stronger KRA completion rate.
    s_rate = strong.kra_submitted / max(1, strong.eligible_employees)
    w_rate = struggling.kra_submitted / max(1, struggling.eligible_employees)
    assert s_rate >= w_rate - 0.05


def test_seed_census_persist_and_metrics(tmp_path=None):
    with SessionLocal() as db:
        reset_org(db)
        # Ensure companies exist for FK-less census (employees are keyed by code only).
        from app.db.models import Company

        for code, name in (("LTF", "L&T Finance"), ("LTIM", "LTIMindtree")):
            if not db.scalar(select(Company.id).where(Company.code == code)):
                db.add(Company(code=code, name=name))
        db.commit()

        summary = seed_census(
            db,
            [("LTF", "steady"), ("LTIM", "strong")],
            per_ic=90,
            seed="persist-v1",
            clear=True,
        )
        assert summary["employees"]["LTF"] > 90
        assert summary["employees"]["LTIM"] > 90
        n = db.scalar(select(func.count()).select_from(Employee)) or 0
        assert n == summary["employees"]["LTF"] + summary["employees"]["LTIM"]
        assert db.scalar(select(func.count()).select_from(EmployeePerformance)) or 0 > 0
        assert db.scalar(select(func.count()).select_from(EmployeeEvent)) or 0 > 0
        mcd = {
            r.company_code: r
            for r in db.scalars(select(MockCompanyData))
        }
        assert set(mcd) == {"LTF", "LTIM"}
        assert mcd["LTIM"].origin == "census"

        metrics = compute_metrics(db, "LTIM")
        assert metrics["available"] is True
        m = metrics["metrics"]
        assert m["headcount_active"] > 0
        assert m["attrition"]["attrition_pct"] is not None
        assert m["manager_health"]["managers_with_reports"] >= 1
        assert m["skills_learning"]["role_skill_coverage_pct"] is not None
        assert m["talent"]["trainees_active"] >= 0
        assert metrics["inventable_examples"]

        # Re-aggregate from DB-derived path via stored raw consistency:
        from app.ingestion.stubgen import CompanyRaw

        stored = CompanyRaw(**mcd["LTIM"].raw)
        problems = validate(stored)
        assert problems == [], problems

        wiped = reset_org(db)
        assert wiped.get("employees", 0) > 0
        assert (db.scalar(select(func.count()).select_from(Employee)) or 0) == 0
        assert (db.scalar(select(func.count()).select_from(MockCompanyData)) or 0) == 0


def test_persist_batch_roundtrip_counts():
    batch = simulate_ic("LTR", "steady", n=85, seed="rt-v1")
    with SessionLocal() as db:
        reset_org(db)
        n = persist_batch(db, batch)
        db.commit()
        assert n == len(batch.employees)
        assert (db.scalar(
            select(func.count()).select_from(Employee).where(Employee.company_code == "LTR")
        ) or 0) == n
        reset_org(db)


def test_simulate_group_covers_lnt_codes():
    batches = simulate_group(
        [("LTF", "steady"), ("LTMR", "struggling"), ("LTR", "steady"),
         ("LTTS", "strong"), ("LTIM", "strong")],
        per_ic=95,
        seed="group-v1",
    )
    assert len(batches) == 5
    for b in batches:
        assert validate(to_company_raw(b)) == []
