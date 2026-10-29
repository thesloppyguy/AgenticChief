import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.approvals import router as approvals_router
from app.api.assets import agents_router, skills_router
from app.api.auth import router as auth_router
from app.api.connections import router as connections_router
from app.api.copilot import router as copilot_router
from app.api.documents import router as documents_router
from app.api.ingestion import router as ingestion_router
from app.api.memories import router as memories_router
from app.api.pins import router as pins_router
from app.api.routes import router
from app.api.schedules import router as schedules_router
from app.api.scorecard_config import router as scorecard_config_router
from app.api.workflows import router as workflows_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.db.migrate import assert_schema_current
    from app.db.session import SessionLocal, engine
    from app.workflows.engine import sweep_stale

    with engine.connect() as conn:
        assert_schema_current(conn)  # deliberately not swallowed: a stale schema must stop the server
    try:
        from app.assets.builtin import seed_builtin as seed_assets
        from app.knowledge.builtin import seed_builtin as seed_docs

        with SessionLocal() as db:
            seed_docs(db)  # idempotent: keeps the built-in reference documents in step with the code
            seed_assets(db)  # and the built-in skills and agent
    except Exception:
        logging.getLogger(__name__).exception("seeding built-in documents/skills failed")
    try:
        # Runs whose worker died (no heartbeat) are marked interrupted so they can be resumed.
        with SessionLocal() as db:
            n = sweep_stale(db)  # heartbeat-based, so another live instance's run is left alone
            if n:
                logging.getLogger(__name__).warning("marked %d interrupted workflow run(s)", n)
    except Exception:
        logging.getLogger(__name__).exception("startup workflow sweep failed")
    task = None
    if settings.scheduler_enabled:
        import asyncio

        from app.api.workflows import get_llm
        from app.scheduler.runner import loop

        task = asyncio.create_task(loop(SessionLocal, lambda: {"factory": SessionLocal, "llm": get_llm()}))
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="CHRO Copilot API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(router)
app.include_router(copilot_router)
app.include_router(ingestion_router)
app.include_router(approvals_router)
app.include_router(alerts_router)
app.include_router(workflows_router)
app.include_router(connections_router)
app.include_router(scorecard_config_router)
app.include_router(pins_router)
app.include_router(documents_router)
app.include_router(skills_router)
if settings.mock_sources_enabled:  # stand-ins for the real source systems; never on by default
    from app.mock_sources.router import router as mock_sources_router

    app.include_router(mock_sources_router)
app.include_router(agents_router)
app.include_router(schedules_router)
app.include_router(memories_router)
