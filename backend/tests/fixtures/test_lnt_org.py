"""L&T Group CHRO org model + demo RNG smoke (in-memory DB)."""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import Role, make_token
from app.db.models import Company, Department, Goal, Person
from app.org.companies import LNT_CODES, LNT_COMPANIES
from scripts.seed import ensure_companies
from tests.api.conftest import client  # noqa: F401


def h(user="admin", role=Role.ADMIN):
    return {"Authorization": f"Bearer {make_token(user, role)}"}


def test_ensure_companies_seeds_five_lnt(client):
    from app.db.session import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    # conftest already inserted IC1..3 — wipe via reset then ensure
    from app.org.reset import reset_org

    reset_org(db)
    ensure_companies(db)
    rows = list(db.scalars(select(Company)))
    codes = sorted(c.code for c in rows)
    assert codes == sorted(LNT_CODES)
    names = {c.code: c.name for c in rows}
    assert names["LTTS"] == "L&T Technology Services"
    assert names["LTMR"] == "L&T Metro Rail"


def test_org_apis_and_rng_monitoring(client):
    from app.db.session import get_db
    from app.main import app

    db = next(app.dependency_overrides[get_db]())
    from app.org.reset import reset_org

    reset_org(db)
    ensure_companies(db)
    p = Person(
        full_name="Ananya Krishnan",
        role="Group CHRO",
        email="ananya.krishnan@example.com",
        company_code=None,
        is_principal=True,
        authority_scope=["wildcard"],
        department_slugs=["people"],
    )
    db.add(p)
    db.flush()
    d = Department(
        slug="people",
        title="Group People",
        company_code=None,
        specialist_key="chro",
        head_person_id=p.id,
        authority_level="propose_only",
        headcount=10,
    )
    db.add(d)
    db.flush()
    db.add(
        Goal(
            department_id=d.id,
            period_type="quarter",
            period_value="Q3",
            key_result="Retention above green",
            target=">=90%",
            current="81%",
            status="at_risk",
            pillar_key="retention",
        )
    )
    db.commit()

    r = client.get("/people", headers=h())
    assert r.status_code == 200 and any(x["full_name"] == "Ananya Krishnan" for x in r.json())
    r = client.get("/goals", headers=h())
    assert r.status_code == 200 and r.json()[0]["status"] == "at_risk"

    r = client.post("/demo/rng/scorecard", headers=h(), json={"period": "2026-10", "seed": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["records_written"] > 0
    assert len(body["companies"]) == len(LNT_COMPANIES)

    r = client.get("/demo/rng/monitoring", params={"period": "2026-10"}, headers=h())
    assert r.status_code == 200
    assert r.json()["group"]["score"] is not None

    r = client.get("/demo/rng/sources/successfactors", params={"company_code": "LTTS"}, headers=h())
    assert r.status_code == 200 and "d" in r.json()


def test_fixtures_list(client):
    r = client.get("/fixtures", headers=h())
    assert r.status_code == 200
    assert len(r.json()["companies"]) == 5
