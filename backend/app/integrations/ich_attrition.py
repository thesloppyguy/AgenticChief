"""SAP CPI ICHRATTRITION client: XML IC trigger → JSON MyzoneData.Employee."""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.core.config import IntegrationConfig

SOURCE_KEY = "ichrattrition"


def build_trigger_xml(ic_code: str) -> str:
    """Build `<Trigger><IC>CODE</IC></Trigger>` body for CPI."""
    root = ET.Element("Trigger")
    ic = ET.SubElement(root, "IC")
    ic.text = ic_code.strip().upper()
    return ET.tostring(root, encoding="unicode")


def _auth_headers(cfg: IntegrationConfig) -> dict[str, str]:
    if cfg.auth == "basic" and cfg.username and cfg.password:
        raw = f"{cfg.username}:{cfg.password.get_secret_value()}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
    if cfg.auth == "bearer" and cfg.token:
        return {"Authorization": f"Bearer {cfg.token.get_secret_value()}"}
    raise ValueError(f"{SOURCE_KEY}: credentials for auth={cfg.auth} are not configured")


def parse_employees(payload: Any) -> list[dict[str, Any]]:
    """Extract Employee list from MyzoneData response (list or single object)."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if not isinstance(payload, dict):
        return []
    myzone = payload.get("MyzoneData") or payload.get("myzoneData") or payload
    if not isinstance(myzone, dict):
        return []
    employees = myzone.get("Employee") or myzone.get("employee") or []
    if isinstance(employees, dict):
        return [employees]
    if isinstance(employees, list):
        return [e for e in employees if isinstance(e, dict)]
    return []


def _s(row: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        text = str(v).strip()
        if text:
            return text
    return ""


def _date_or_none(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    # Accept YYYY-MM-DD or longer ISO timestamps
    return text[:10]


def _parse_bool(value: str) -> bool | None:
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in ("true", "1", "yes", "y"):
        return True
    if text in ("false", "0", "no", "n"):
        return False
    return None


def _months_between(start: str | None, end: date | None = None) -> int:
    if not start:
        return 0
    try:
        y, m, d = (int(x) for x in start[:10].split("-"))
        s = date(y, m, d)
    except (TypeError, ValueError):
        return 0
    e = end or date.today()
    return max(0, (e.year - s.year) * 12 + (e.month - s.month))


def map_employee_row(row: dict[str, Any], *, synced_at: datetime | None = None) -> dict[str, Any]:
    """Map one CPI Employee dict → AttritionEmployee column kwargs."""
    employee_id = _s(row, "EMPLOYEEID", "EmployeeId", "PSNUMBER")
    ic = _s(row, "IC").upper()
    hire = _date_or_none(_s(row, "DATEOFHIRING", "DATEOFJOINING"))
    joining = _date_or_none(_s(row, "DATEOFJOINING", "DATEOFHIRING"))
    separation = _date_or_none(_s(row, "SEPERATIONDATE", "SEPARATIONDATE"))
    last_working = _date_or_none(_s(row, "LASTWORKINGDATE"))
    dept_code = _s(row, "DEPARTMENT")
    dept_desc = _s(row, "DEPARTMENTDESCRIPTION")
    department = dept_desc or dept_code
    if dept_code and dept_desc and dept_code != dept_desc:
        department = f"{dept_code} — {dept_desc}"
    job_family = _s(row, "JOBFAMILY")
    job_sub = _s(row, "JOBSUBFAMILYDESC", "JOBSUBFAMILY")
    job_function = job_family
    if job_family and job_sub:
        job_function = f"{job_family} / {job_sub}"
    grade = _s(row, "GRADE", "PAYGRADE")
    trainee_exp = _s(row, "TRAINEEEXPERIENCE")
    emp_group = _s(row, "EMPLOYEEGROUPDESC", "EMPLOYEEGROUP")
    is_trainee = "trainee" in emp_group.lower() or (
        bool(trainee_exp) and trainee_exp not in ("00Y00M", "0Y0M", "00Y0M")
    )
    status = "separated" if separation else "active"
    ok_rehire = _parse_bool(_s(row, "OKTOREHIRE"))
    now = synced_at or datetime.now(timezone.utc)

    return {
        "employee_id": employee_id,
        "company_code": ic,
        "ic_description": _s(row, "ICDESCRIPTION"),
        "legal_entity": _s(row, "LEGALENTITY"),
        "country": _s(row, "COUNTRYOFCOMPANY"),
        "sbg": _s(row, "SBG"),
        "business_unit": _s(row, "BUSINESSUNIT"),
        "department": department,
        "department_code": dept_code,
        "base_location": _s(row, "BASELOCATION"),
        "pay_grade": _s(row, "PAYGRADE"),
        "grade": grade,
        "band": _s(row, "BAND"),
        "appointment_type": _s(row, "APPOINTMENTTYPE"),
        "employee_group": emp_group,
        "employment_type": None,  # not in current API
        "hire_date": hire,
        "joining_date": joining,
        "trainee_experience": trainee_exp or None,
        "contract_training_end_date": _date_or_none(_s(row, "CONTRACTTRAININGENDDATE")),
        "separation_date": separation,
        "payroll_end_date": None,
        "notice_period": _s(row, "NOTICEPERIOD") or None,
        "notice_period_policy": _s(row, "NOTICEPERIODPOLICY") or None,
        "resignation_date": _date_or_none(_s(row, "RESIGNATIONDATE")),
        "last_working_date": last_working,
        "request_relieving_date": _date_or_none(_s(row, "REQUESTRELIEVINGDATE")),
        "doj_resignation_port": _date_or_none(_s(row, "DOJ_RESIPORT")),
        "resignation_reason": None,
        "manager_user_id": _s(row, "MANAGERUSERID") or None,
        "manager_name": _s(row, "MANAGERNAME") or None,
        "job_family": job_family or None,
        "job_subfamily": _s(row, "JOBSUBFAMILY") or None,
        "job_subfamily_desc": _s(row, "JOBSUBFAMILYDESC") or None,
        "job_function": job_function or None,
        "ok_to_rehire": ok_rehire,
        "exit_interview_required": None,
        "date_of_joining_exit_port": _date_or_none(_s(row, "DATEOFJOINING_EXITPORT")),
        "date_of_separation_exit_port": _date_or_none(_s(row, "DATEOFSEPARATION_EXITPORT")),
        "exit_designation": None,
        "exit_tenure": None,
        "exit_trigger_hr": None,
        "exit_trigger_employee": None,
        "exit_flag_compensation": None,
        "exit_flag_brand": None,
        "exit_flag_role": None,
        "exit_flag_culture": None,
        "exit_recommend_friends": None,
        "exit_would_rejoin": None,
        "current_cadre": None,
        "mvg_rating": None,
        "cp_rating": None,
        "pdr_rating": None,
        "status": status,
        "is_trainee": is_trainee,
        "time_in_company_months": _months_between(joining or hire),
        "synced_at": now,
        "raw": row,
    }


class IchAttritionClient:
    """HTTP client for ICHRATTRITION CPI endpoint."""

    def __init__(self, cfg: IntegrationConfig, transport: httpx.BaseTransport | None = None):
        if not cfg.enabled:
            raise ValueError(f"{SOURCE_KEY} integration is disabled")
        if not cfg.base_url:
            raise ValueError(f"{SOURCE_KEY}: base_url is required")
        self._cfg = cfg
        self._http = httpx.Client(
            timeout=cfg.timeout_s,
            transport=transport or httpx.HTTPTransport(retries=1),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> IchAttritionClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_ic(self, ic_code: str) -> list[dict[str, Any]]:
        """GET with XML body; return mapped-ready raw employee dicts."""
        body = build_trigger_xml(ic_code)
        headers = {
            "Content-Type": "application/xml",
            "Accept": "application/json, application/xml, text/xml, */*",
            **_auth_headers(self._cfg),
        }
        # CPI docs use GET with a body (unusual); httpx supports content= on request().
        resp = self._http.request("GET", self._cfg.base_url, content=body.encode(), headers=headers)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "json" in ctype or resp.text.lstrip().startswith(("{", "[")):
            return parse_employees(resp.json())
        # Some tenants wrap JSON in text/plain
        try:
            return parse_employees(resp.json())
        except Exception as exc:
            raise ValueError(f"{SOURCE_KEY}: unexpected response for {ic_code}: {resp.text[:200]}") from exc
