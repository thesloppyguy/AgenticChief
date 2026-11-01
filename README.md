# AgenticChief

Group HR Scorecard with an OpenExecutive-style multi-agent Copilot: code-registered specialists, Markdown skills, built-in scorecard tools, and MCP connectors via `mcp_servers.json`.

```
backend/   FastAPI + SQLAlchemy + Alembic, SQLite   (Python 3.12+, uv)
frontend/  Next.js 16 App Router + Tailwind         (pnpm)
e2e/       Playwright browser smoke test
docker/    compose file (api + web)
```

## Quick start

```bash
# backend
cd backend
uv sync
uv run python -m scripts.seed_integrations
uv run python -m scripts.dev_token admin
uv run uvicorn app.main:app --reload            # http://localhost:8000

# frontend
cd frontend
pnpm install && pnpm dev                        # http://localhost:3000
```

## Agents, Skills, Tools, Connectors, MCP

| Surface | Implementation |
|---|---|
| **Agents** | Code registry under `app/agents/` (CSO, CFO, CHRO, …). Overrides in SQLite (`agent_overrides`). UI: Settings → Agents. |
| **Skills** | Markdown + YAML frontmatter under `app/knowledge/builtin/skills/` (and `company/skills/`). Indexed in ChromaDB. UI: Settings → Skills. |
| **Tools** | Executive schema+handler maps: `consult_specialist`, skill search/load, scorecard tools, optional MCP tools. Custom tools: Settings → Tools. |
| **Connectors** | Env + `company/mcp_servers.json` (see `mcp_servers.json.example`). UI: Settings → Connectors / MCP Tools. |
| **MCP** | Gateway (stdio children, MCP 2.x) when `MCP_ENABLED=true`; server mounted at `/mcp`. |

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

## Scorecard

Deterministic HR scoring (7 pillars, 23 KPIs) is unchanged. Live/stub/manual ingestion remains; the old capability-registry KPI mapping path was removed with the OE port.

## Governance

Approvals still gate consequential actions (reminders, snapshots, monthly report publish, workflow publish, scorecard rule activation). Skills and agents are no longer DB-published assets.
