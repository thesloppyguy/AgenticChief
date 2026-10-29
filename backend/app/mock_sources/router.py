"""HTTP endpoints that stand in for the real source systems. Mounted only when MOCK_SOURCES_ENABLED is on.

Data comes from AI-generated company profiles (see store.py). A request for a company the platform does not
know gets an empty row and never triggers generation, so arbitrary input cannot run up AI spend.
"""
from __future__ import annotations

import hmac
import re
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from app.api.workflows import get_session_factory
from app.audit.logger import audit
from app.core.config import settings
from app.core.security import Principal, require_admin
from app.db.models import MockCompanyData
from app.db.session import get_db
from app.ingestion.sources import SOURCE_KPIS
from app.ingestion.stub import StubExtractor
from app.ingestion.stubgen import CompanyRaw

from . import store
from .catalog import STYLES

router = APIRouter(prefix="/mock-sources", tags=["mock-sources"])
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

JOB: dict = {"running": False, "started_at": None, "finished_at": None, "done": 0, "total": 0, "result": None}
_job_lock = threading.Lock()


def get_ai_client():
    """The model client used to generate profiles, or None when no key is configured."""
    if not settings.anthropic_api_key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)


def source_auth(request: Request) -> None:
    """The mock systems have their own bearer token, like a real vendor API. It is not a platform login."""
    if settings.mock_source_token is None:
        raise HTTPException(503, "MOCK_SOURCE_TOKEN is not configured")
    sent = request.headers.get("authorization", "")
    if not hmac.compare_digest(sent.encode(), f"Bearer {settings.mock_source_token.get_secret_value()}".encode()):
        raise HTTPException(401, "invalid or missing bearer token")


def _admin(who: Principal = Depends(require_admin)) -> Principal:
    if who.company_ids is not None:
        raise HTTPException(403, "Group-wide scope required")
    return who


def _register(source: str, kpi: str) -> None:
    style = STYLES[source]

    def handler(request: Request, db: Session = Depends(get_db), client=Depends(get_ai_client), _=Depends(source_auth)):
        try:
            company, period = style.parse(dict(request.query_params))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if not _PERIOD.match(period):
            raise HTTPException(422, "period must be YYYY-MM")
        if not store.known_company(db, company):  # unknown company: an empty result, and no AI call
            return JSONResponse(style.wrap(None), headers={"X-Data-Origin": "none"})
        try:
            prof = store.ensure_one(db, client, company)
        except store.GenerationUnavailable as e:
            raise HTTPException(503, str(e)) from e
        raw = StubExtractor(source, {company: CompanyRaw(**prof.raw)}).fetch(company, period)[kpi]
        row = {style.field(k): v for k, v in raw.items()}
        return JSONResponse(style.wrap(row), headers={"X-Data-Origin": prof.origin})

    # The router already carries the /mock-sources prefix, so register relative to it (catalog.prefix() is for clients).
    router.add_api_route(f"/{source}" + style.path(kpi), handler, methods=["GET"], name=f"{source}:{kpi}")


for _source, _kpis in SOURCE_KPIS.items():
    for _kpi in dict.fromkeys(_kpis):  # MyHealth and Hi5Plus have a single shared endpoint per KPI
        _register(_source, _kpi)


@router.get("/admin/status")
def status(db: Session = Depends(get_db), _: Principal = Depends(_admin)):
    return {**store.status(db), "job": dict(JOB), "token_configured": settings.mock_source_token is not None,
            "ai_configured": bool(settings.anthropic_api_key), "fallback_allowed": settings.mock_sources_allow_fallback}


@router.post("/admin/generate", status_code=202)
def generate(factory: sessionmaker = Depends(get_session_factory), client=Depends(get_ai_client),
             who: Principal = Depends(_admin)):
    """Generate every missing company profile with Claude, in the background."""
    if client is None:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured")
    with _job_lock:
        if JOB["running"]:
            raise HTTPException(409, "A generation run is already in progress")
        JOB.update(running=True, started_at=datetime.now(UTC).isoformat(timespec="seconds"), finished_at=None, done=0,
                   total=0, result=None)

    def work() -> None:
        try:
            with factory() as db:
                audit(db, who, "mock_sources_generate")
                db.commit()
            r = store.generate_missing(factory, client, lambda n: JOB.update(done=n))
            JOB["result"] = {"ai": r.ai, "fallback": r.fallback, "failed": r.failed, "notes": r.notes[:10]}
        except Exception as e:  # noqa: BLE001 - recorded by type; the thread must always clear the flag
            JOB["result"] = {"error": type(e).__name__}
        finally:
            JOB.update(running=False, finished_at=datetime.now(UTC).isoformat(timespec="seconds"))

    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


@router.delete("/admin/data", status_code=204)
def reset(db: Session = Depends(get_db), who: Principal = Depends(_admin)):
    """Forget all generated profiles, so the next request or run generates fresh ones."""
    if JOB["running"]:
        raise HTTPException(409, "A generation run is in progress")
    db.query(MockCompanyData).delete()
    audit(db, who, "mock_sources_reset")
    db.commit()
