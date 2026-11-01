# AgenticChief

Group HR Scorecard with an OpenExecutive-style multi-agent Copilot: code-registered specialists, Markdown skills, built-in scorecard tools, and MCP connectors via `mcp_servers.json`.

Demo shape: **L&T Group CHRO** with five Independent Companies (LTF, LTMR, LTR, LTTS, LTIM), People/Departments/Goals, fixture-backed workforce pulse (skills/succession), seeded memory, CHRO workflows/watches/approvals, and chat KPI artifacts.

```
backend/   FastAPI + SQLAlchemy + Alembic, SQLite   (Python 3.12+, uv)
frontend/  Next.js 16 App Router + Tailwind         (pnpm)
seed/      OE-shaped L&T Group + IC fixtures
e2e/       Playwright browser smoke test
docker/             compose + Dokploy notes (api + web)
```

## Quick start

```bash
# backend
cd backend
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_lnt --reset          # wipe + load L&T demo (preferred)
# or: uv run python -m scripts.seed_integrations --reset
uv run python -m scripts.dev_token admin
uv run uvicorn app.main:app --reload            # http://localhost:8000

# frontend
cd frontend
pnpm install && pnpm dev                        # http://localhost:3000
```

### Docker / Dokploy

```bash
# from repo root — API migrates + seeds L&T demo on first /data volume, then serves
docker compose -f docker/docker-compose.yml up --build
```

Dokploy setup (two apps or Compose): [docker/README.md](docker/README.md).

In the UI: **Settings → Company → Load L&T demo** (admin), or `POST /fixtures/lnt/load`.

## Agents, Skills, Tools, Connectors, MCP

| Surface | Implementation |
|---|---|
| **Agents** | Code registry under `app/agents/` (CSO, CFO, CHRO, …). Overrides in SQLite (`agent_overrides`). UI: Settings → Agents. |
| **Skills** | Markdown + YAML frontmatter under `app/knowledge/builtin/skills/` (and `company/skills/`). Indexed in ChromaDB. UI: Settings → Skills. |
| **Tools** | Executive schema+handler maps: `consult_specialist`, skill search/load, scorecard + org tools, optional MCP tools. Custom tools: Settings → Tools. |
| **Connectors** | Env + `company/mcp_servers.json` (see `mcp_servers.json.example`). UI: Settings → Connectors / MCP Tools. |
| **MCP** | Gateway (stdio children, MCP 2.x) when `MCP_ENABLED=true`; server mounted at `/mcp`. |
| **Org** | People / Departments / Goals (`GET /people`, `/departments`, `/goals`). Roster emails are `@example.com` demo targets (OE-style); login remains open admin JWT. |
| **Workforce** | Fixture APIs `/workforce/pulse|skills|succession|actions` + Executive tools; Home pulse strip; chat charts with Export / Schedule. |
| **Demo RNG** | `/demo/rng/*` (admin; requires `STUB_DATA_ENABLED` or `DEMO_RNG_ENABLED`). |

Architecture reference: [OpenExecutive.md](OpenExecutive.md).

### Notable env

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Defaults to SQLite under `backend/data/`. |
| `JWT_SECRET` | Signing key (32+ characters). |
| `ANTHROPIC_API_KEY` | Executive, specialists, evals. |
| `MCP_ENABLED` | Boot the MCP gateway (`false` by default). |
| `MCP_SERVERS_PATH` | Path to `mcp_servers.json`. |
| `VECTOR_STORE_PATH` | Chroma persist directory. |
| `STUB_DATA_ENABLED` | Stub ingestion + `/demo/rng/*` (default true). |
| `DEMO_RNG_ENABLED` | Force-enable RNG endpoints even if stub data is off. |
| `MOCK_SOURCES_ENABLED` | Serve AI-backed stand-in HR APIs at `/mock-sources/*` (default false). |
| `SOURCE_FRESHNESS_SLA_HOURS` | Hours before a source is marked stale (default 72). |

## AI-backed live sources (optional)

Offline default uses the stub fixture. To exercise the live adapters without real SuccessFactors / PeopleStrong / MyHealth / Hi5Plus tenants:

```bash
cd backend
uv run python -m scripts.setup_mock_sources --write-env   # mappings + .env INTEGRATIONS__* → localhost
# restart the API, then as admin:
#   POST /mock-sources/admin/generate   # Claude builds company profiles once (costs tokens)
#   POST /sources/sync  {"period":"2026-10"}   # or Settings → Connectors → HR Sources → Sync
```

`GET /sources/status` reports mode (`live`|`stub`|`disabled`), freshness (`fresh`|`stale`|`never`), and `data_origin` (`ai` when mock profiles supplied the numbers).

## Scorecard

Deterministic HR scoring (7 pillars, 23 KPIs) per [CHRO.md](CHRO.md). Five L&T ICs on the Group scorecard; live/stub/manual ingestion remains.

## Governance

Approvals gate consequential actions: KPI reminders and company-wide directives (queued `OutboundMessage` to People), capability / retention launches (arm 90-day watches), schedule_report, snapshots, monthly report publish, workflow publish, scorecard rule activation. Skills and agents are not DB-published assets. CHRO workflow defs (`weekly_workforce_brief`, `performance_review`, `comp_refresh`, …) ship as seeded workflow assets.
