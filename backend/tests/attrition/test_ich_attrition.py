"""ICHRATTRITION mapper + mocked sync API."""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.core.config import IntegrationConfig, settings as app_settings
from app.core.security import Role, make_token
from app.db.models import AttritionEmployee, Company, Employee
from app.integrations.ich_attrition import (
    build_trigger_xml,
    map_employee_row,
    parse_employees,
)
from app.org.companies import LNT_CODES
from scripts.seed import ensure_companies
from tests.api.conftest import client  # noqa: F401

SAMPLE = {
    "MyzoneData": {
        "Employee": [
            {
                "EMPLOYEEID": "20375100",
                "COUNTRYOFCOMPANY": "TZA",
                "DATEOFHIRING": "2024-10-11",
                "APPOINTMENTTYPE": "D",
                "TRAINEEEXPERIENCE": "00Y00M",
                "DATEOFJOINING": "2024-10-11",
                "CONTRACTTRAININGENDDATE": "2026-10-10",
                "NOTICEPERIOD": "",
                "SEPERATIONDATE": "2026-11-12",
                "LEGALENTITY": "",
                "IC": "WETI",
                "ICDESCRIPTION": "Water & Effluent Treatment – International SBG",
                "SBG": "International WET",
                "BUSINESSUNIT": "Effluent Treatment BU",
                "DEPARTMENT": "LE22M349",
                "DEPARTMENTDESCRIPTION": "Construction, Testing and Commissioning of Water",
                "BASELOCATION": "Tanzania",
                "PAYGRADE": "O2",
                "GRADE": "O2",
                "BAND": "E Band",
                "MANAGERUSERID": "83798",
                "MANAGERNAME": "Ganesh P",
                "RESIGNATIONDATE": "",
                "LASTWORKINGDATE": "",
                "REQUESTRELIEVINGDATE": "",
                "NOTICEPERIODPOLICY": "",
                "DOJ_RESIPORT": "",
                "JOBFAMILY": "Execution",
                "JOBSUBFAMILY": "500000052",
                "JOBSUBFAMILYDESC": "Civil and Structural",
                "EMPLOYEEGROUPDESC": "Permanent",
                "OKTOREHIRE": "true",
                "DATEOFJOINING_EXITPORT": "",
                "DATEOFSEPARATION_EXITPORT": "",
            },
            {
                "EMPLOYEEID": "173226",
                "COUNTRYOFCOMPANY": "SAU",
                "DATEOFHIRING": "2006-12-22",
                "APPOINTMENTTYPE": "L",
                "TRAINEEEXPERIENCE": "",
                "DATEOFJOINING": "2006-12-22",
                "CONTRACTTRAININGENDDATE": "",
                "NOTICEPERIOD": "",
                "SEPERATIONDATE": "2026-11-12",
                "LEGALENTITY": "LARSEN & TOUBRO SAUDI ARABIA LLC",
                "IC": "WETI",
                "ICDESCRIPTION": "Water & Effluent Treatment – International SBG",
                "SBG": "International WET",
                "BUSINESSUNIT": "Water Treatment (Desalination) BU",
                "DEPARTMENT": "LE25D035",
                "DEPARTMENTDESCRIPTION": "Ras Mohaisen Project UJV",
                "BASELOCATION": "KSA",
                "PAYGRADE": "M3-B",
                "GRADE": "M3B",
                "BAND": "Tier 3",
                "MANAGERUSERID": "244327",
                "MANAGERNAME": "RAJESH M",
                "RESIGNATIONDATE": "",
                "LASTWORKINGDATE": "",
                "REQUESTRELIEVINGDATE": "",
                "NOTICEPERIODPOLICY": "",
                "DOJ_RESIPORT": "",
                "JOBFAMILY": "Execution",
                "JOBSUBFAMILY": "500000052",
                "JOBSUBFAMILYDESC": "Civil and Structural",
                "EMPLOYEEGROUPDESC": "Permanent",
                "OKTOREHIRE": "true",
                "DATEOFJOINING_EXITPORT": "",
                "DATEOFSEPARATION_EXITPORT": "",
            },
        ]
    }
}


def h(user="admin", role=Role.ADMIN):
    return {"Authorization": f"Bearer {make_token(user, role)}"}


def test_build_trigger_xml():
    xml = build_trigger_xml("weti")
    assert "<IC>WETI</IC>" in xml
    assert xml.startswith("<Trigger>")


def test_parse_and_map_sample():
    rows = parse_employees(SAMPLE)
    assert len(rows) == 2
    mapped = map_employee_row(rows[0])
    assert mapped["employee_id"] == "20375100"
    assert mapped["company_code"] == "WETI"
    assert mapped["separation_date"] == "2026-11-12"
    assert mapped["status"] == "separated"
    assert mapped["ok_to_rehire"] is True
    assert mapped["grade"] == "O2"
    assert "LE22M349" in mapped["department"]
    assert mapped["resignation_reason"] is None


def _mock_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    body = request.content.decode()
    assert "<IC>" in body
    if "<IC>WETI</IC>" in body:
        return httpx.Response(200, json=SAMPLE)
    return httpx.Response(200, json={"MyzoneData": {"Employee": []}})


def test_sync_with_mock_transport(client, monkeypatch):
    from app.attrition.sync import sync_attrition
    from app.db.session import get_db
    from app.main import app
    from app.org.reset import reset_org

    db = next(app.dependency_overrides[get_db]())
    reset_org(db)
    ensure_companies(db)

    cfg = IntegrationConfig(
        enabled=True,
        base_url="https://cpi.example/http/ICHRATTRITION",
        auth="basic",
        username="user",
        password="pass",
    )
    monkeypatch.setitem(app_settings.integrations, "ichrattrition", cfg)

    result = sync_attrition(
        db,
        ics=["WETI", "PTD"],
        triggered_by="test",
        transport=httpx.MockTransport(_mock_handler),
    )
    assert result["status"] in ("ok", "partial")
    assert "WETI" in result["ics_ok"]
    assert result["rows_upserted"] == 2

    rows = list(db.scalars(select(AttritionEmployee).where(AttritionEmployee.company_code == "WETI")))
    assert {x.employee_id for x in rows} == {"20375100", "173226"}

    weti = db.scalar(select(Company).where(Company.code == "WETI"))
    assert weti is not None
    assert "Water" in weti.name

    emp = db.scalar(select(Employee).where(Employee.ps_number == "20375100"))
    assert emp is not None and emp.company_code == "WETI" and emp.status == "separated"

    st = client.get("/attrition/status", headers=h())
    assert st.status_code == 200
    status = st.json()
    assert status["total_rows"] >= 2
    assert status["rows_by_ic"].get("WETI") == 2
    assert status["last_sync"]["rows_upserted"] == 2
    assert len(status["ic_roster"]) == len(LNT_CODES)


def test_sync_api_uses_client(client, monkeypatch):
    """POST /attrition/sync wires through with a mocked IchAttritionClient."""
    from app.attrition import sync as sync_mod
    from app.integrations.ich_attrition import IchAttritionClient

    cfg = IntegrationConfig(
        enabled=True,
        base_url="https://cpi.example/http/ICHRATTRITION",
        auth="basic",
        username="user",
        password="pass",
    )
    monkeypatch.setitem(app_settings.integrations, "ichrattrition", cfg)

    class Wrapped(IchAttritionClient):
        def __init__(self, cfg, transport=None):
            super().__init__(cfg, transport=httpx.MockTransport(_mock_handler))

    monkeypatch.setattr(sync_mod, "IchAttritionClient", Wrapped)

    r = client.post("/attrition/sync", headers=h(), json={"ics": ["WETI"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["rows_upserted"] == 2


def test_sync_disabled_returns_error_run(client, monkeypatch):
    monkeypatch.setitem(
        app_settings.integrations,
        "ichrattrition",
        IntegrationConfig(enabled=False),
    )
    r = client.post("/attrition/sync", headers=h(), json={"ics": ["WETI"]})
    assert r.status_code == 200
    assert r.json()["status"] == "error"
