import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.alerts import router as alerts_router
from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.briefs import router as briefs_router
from app.api.company_profile import router as company_profile_router
from app.api.copilot import router as copilot_router
from app.api.demo_rng import router as demo_rng_router
from app.api.documents import router as documents_router
from app.api.fixtures import router as fixtures_router
from app.api.ingestion import router as ingestion_router
from app.api.sources import router as sources_router
from app.api.memories import router as memories_router
from app.api.oe_skills import router as skills_router
from app.api.org import router as org_router
from app.api.pins import router as pins_router
from app.api.routes import router
from app.api.saved_tools import router as saved_tools_router
from app.api.schedules import router as schedules_router
from app.api.scorecard_config import router as scorecard_config_router
from app.api.setup_status import router as setup_router
from app.api.tools import router as tools_router
from app.api.workflows import router as workflows_router
from app.api.workforce import router as workforce_router
from app.core.config import settings
from app.mcp_server import server as mcp_server
from app.orchestrator.mcp_gateway import boot_gateway, get_active_gateway


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.agents.overrides import initialize_overrides_db
    from app.db.migrate import assert_schema_current
    from app.db.session import SessionLocal, engine
    from app.knowledge.skills_index import seed_builtin_skills
    from app.orchestrator.saved_tools import initialize as init_saved_tools
    from app.workflows.engine import sweep_stale

    with engine.connect() as conn:
        assert_schema_current(conn)
    initialize_overrides_db()
    init_saved_tools()
    try:
        from app.knowledge.builtin import seed_builtin as seed_docs

        with SessionLocal() as db:
            seed_docs(db)
    except Exception:
        logging.getLogger(__name__).exception("seeding built-in documents failed")
    try:
        n = seed_builtin_skills()
        logging.getLogger(__name__).info("skills index: synced %d built-in skill(s)", n)
    except Exception:
        logging.getLogger(__name__).exception("seeding skills index failed")
    try:
        from app.knowledge.loader import remirror_all_company_docs, seed_builtin_knowledge

        n = seed_builtin_knowledge()
        logging.getLogger(__name__).info("builtin knowledge: seeded %d chunk(s)", n)
        with SessionLocal() as db:
            remirror_all_company_docs(db)
    except Exception:
        logging.getLogger(__name__).exception("seeding builtin/company chroma knowledge failed")
    try:
        with SessionLocal() as db:
            n = sweep_stale(db)
            if n:
                logging.getLogger(__name__).warning("marked %d interrupted workflow run(s)", n)
    except Exception:
        logging.getLogger(__name__).exception("startup workflow sweep failed")
    try:
        from app.scheduler.seed_briefs import seed_principal_briefs

        with SessionLocal() as db:
            n = seed_principal_briefs(db)
            if n:
                logging.getLogger(__name__).info("seeded %d brief schedule(s)", n)
    except Exception:
        logging.getLogger(__name__).exception("seeding brief schedules failed")

    await boot_gateway()
    mcp_session = None
    try:
        # FastMCP session manager (required when mounted as a sub-app)
        run_cm = getattr(mcp_server.mcp, "session_manager", None)
        if run_cm is not None and hasattr(run_cm, "run"):
            mcp_session = run_cm.run()
            await mcp_session.__aenter__()
    except Exception:
        logging.getLogger(__name__).exception("MCP session manager failed to start")

    task = None
    if settings.scheduler_enabled:
        import asyncio

        from app.api.workflows import get_async_llm, get_llm
        from app.scheduler.runner import loop

        task = asyncio.create_task(
            loop(
                SessionLocal,
                lambda: {"factory": SessionLocal, "llm": get_llm(), "allm": get_async_llm()},
            )
        )
    try:
        yield
    finally:
        if task:
            task.cancel()
        if mcp_session is not None:
            try:
                await mcp_session.__aexit__(None, None, None)
            except Exception:
                logging.getLogger(__name__).exception("MCP session manager shutdown failed")
        gateway = get_active_gateway()
        if gateway is not None:
            try:
                await gateway.stop()
            except Exception:
                logging.getLogger(__name__).exception("MCP gateway shutdown failed")


app = FastAPI(title="AgenticChief API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(auth_router)
api.include_router(router)
api.include_router(copilot_router)
api.include_router(ingestion_router)
api.include_router(sources_router)
api.include_router(approvals_router)
api.include_router(alerts_router)
api.include_router(workflows_router)
api.include_router(scorecard_config_router)
api.include_router(pins_router)
api.include_router(documents_router)
api.include_router(skills_router)
api.include_router(agents_router)
api.include_router(saved_tools_router)
api.include_router(tools_router)
api.include_router(setup_router)
if settings.mock_sources_enabled:
    from app.mock_sources.router import router as mock_sources_router

    api.include_router(mock_sources_router)
api.include_router(schedules_router)
api.include_router(memories_router)
api.include_router(company_profile_router)
api.include_router(briefs_router)
api.include_router(org_router)
api.include_router(workforce_router)
api.include_router(fixtures_router)
api.include_router(demo_rng_router)
app.include_router(api)

mcp_server.mount(app)
