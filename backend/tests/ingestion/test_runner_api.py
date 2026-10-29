import pytest
from sqlalchemy import select

from app.api.ingestion import get_extractors
from app.core.security import Role
from app.db.models import IngestionRun, KpiRecord
from app.db.session import get_db
from app.ingestion.base import Extractor
from app.ingestion.runner import ingest
from app.ingestion.stub import StubExtractor
from app.main import app
from app.services.manual_inputs import MANUAL_KPIS
from tests.api.conftest import auth, client  # noqa: F401

P = "2026-10"


@pytest.fixture()
def db(client):
    gen = app.dependency_overrides[get_db]()
    d = next(gen)
    yield d
    d.close()


def test_ingest_writes_lineage_is_idempotent_and_skips_manual(db):
    from app.db.models import Company
    cid = db.scalar(select(Company.id).where(Company.code == "IC1"))
    # a manual value that an extractor must never overwrite or touch
    db.add(KpiRecord(company_id=cid, kpi_key="gptw_score", period=P, achievement=77, source="manual"))
    db.commit()
    ex = {"successfactors": StubExtractor("successfactors"), "myhealth": StubExtractor("myhealth")}
    s1 = ingest(db, P, ex)
    n1 = db.query(KpiRecord).count()
    s2 = ingest(db, P, ex)
    assert db.query(KpiRecord).count() == n1  # idempotent upsert
    assert [x.status for x in s1] == ["success", "success"]
    rec = db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "kra_submission", KpiRecord.company_id == cid))
    assert rec.source == "successfactors" and rec.detail["mode"] == "stub" and "raw" in rec.detail
    assert rec.numerator is not None and rec.denominator is not None
    assert db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "gptw_score")).achievement == 77
    assert not {r.kpi_key for r in db.scalars(select(KpiRecord)) if r.source != "manual"} & MANUAL_KPIS
    runs = db.scalars(select(IngestionRun)).all()
    assert len(runs) == 4 and all(r.finished_at for r in runs)


class FlakyExtractor(Extractor):
    source, mode, kpis = "hi5plus", "live", ("platform_adoption",)

    def fetch(self, company_code, period):
        if company_code == "IC2":
            raise ConnectionError("secret-host.internal refused")  # must not be stored
        if company_code == "IC3":
            return {"platform_adoption": {"unique_logins": 50, "active_employees": 10}}  # invalid
        return {"platform_adoption": {"unique_logins": 8, "active_employees": 10}}


def test_failures_are_isolated_recorded_without_leaking(db):
    [s] = ingest(db, P, {"hi5plus": FlakyExtractor()})
    assert (s.status, s.companies_ok, s.companies_failed) == ("partial", 1, 2)
    errs = {(e["company"], e["error"]) for e in db.scalars(select(IngestionRun)).one().errors}
    assert errs == {("IC2", "ConnectionError"), ("IC3", "invalid_raw_data")}
    assert "secret-host" not in str(db.scalars(select(IngestionRun)).one().errors)
    rec = db.scalar(select(KpiRecord).where(KpiRecord.kpi_key == "platform_adoption"))
    assert rec.achievement == pytest.approx(80)


def test_api_run_then_scorecard_has_data_and_permissions(client):
    app.dependency_overrides[get_extractors] = lambda: {"successfactors": StubExtractor("successfactors")}
    admin = auth(Role.ADMIN)
    assert client.post("/ingestion/run", json={"period": P}, headers=auth(Role.EDITOR)).status_code == 403
    assert client.post("/ingestion/run", json={"period": P}, headers=auth(Role.ADMIN, [1])).status_code == 403
    assert client.post("/ingestion/run", json={"period": P, "sources": ["nope"]}, headers=admin).status_code == 422
    r = client.post("/ingestion/run", json={"period": P}, headers=admin).json()
    assert r[0]["source"] == "successfactors" and r[0]["status"] == "success"
    sc = client.get("/scorecard", params={"period": P}, headers=admin).json()
    assert sc["group"]["companies_with_data"] == 3
    assert sc["synthetic_data"] is True  # stub-sourced values are flagged
    st = client.get("/ingestion/status", headers=admin).json()
    sf = next(s for s in st if s["source"] == "successfactors")
    assert sf["last_run"]["records_written"] > 0 and sf["live_enabled"] is False
    assert client.get("/ingestion/status", headers=auth(Role.VIEWER)).status_code == 403
    app.dependency_overrides.pop(get_extractors)


def test_status_labels_a_source_whose_data_declares_itself_ai_generated(client, db):
    from app.db.models import Company
    cid = db.scalar(select(Company.id).where(Company.code == "IC1"))
    db.add(KpiRecord(company_id=cid, kpi_key="ahc_completion", period=P, achievement=90, source="myhealth",
                     detail={"mode": "live", "origin": "ai"}))
    db.add(KpiRecord(company_id=cid, kpi_key="platform_adoption", period=P, achievement=80, source="hi5plus", detail={"mode": "live"}))
    db.commit()
    st = {s["source"]: s for s in client.get("/ingestion/status", headers=auth(Role.ADMIN)).json()}
    assert st["myhealth"]["data_origin"] == "ai" and st["hi5plus"]["data_origin"] is None and st["successfactors"]["data_origin"] is None
