# CHRO Copilot

A Group HR Scorecard and AI Copilot for a group of independent companies (88 of them in the reference setup).
Scores are computed by deterministic code, never by the model; the Copilot explains and drills into them.

- **Scorecard:** 7 weighted pillars, 23 sub-KPIs, April–March fiscal year, company and Group views, drill-downs, Excel/CSV export.
- **Copilot:** one assistant (Claude) that answers from the scoring service, searches uploaded documents, and can *propose* actions for human approval.
- **Governance:** anything with side effects goes through a backend-enforced policy and a second admin's approval.

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
uv run python -m scripts.seed_integrations      # creates data/chro.db, migrates it, loads a year of stub data
uv run python -m scripts.dev_token admin        # prints a sign-in token
uv run uvicorn app.main:app --reload            # http://localhost:8000  (OpenAPI at /docs)

# frontend
cd frontend
pnpm install && pnpm dev                        # http://localhost:3000 — paste the token on the login page
```

Sign-in is a pasted JWT for now (SSO is not built). Roles: `admin`, `editor`, `viewer`; a token may be scoped to specific
companies. Create more with `scripts.dev_token <role> [company_id ...]`. Two different admins are needed to exercise approvals.

### Configuration (`backend/.env`, see `.env.example`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Defaults to `sqlite:///backend/data/chro.db`. SQLite is single-writer: run **one** API process. |
| `JWT_SECRET` | Signing key (32+ characters). |
| `ANTHROPIC_API_KEY` | Enables the Copilot, AI commentary, skill/agent evals and AI stub-data generation. Everything else works without it. |
| `INTEGRATIONS__<SOURCE>__ENABLED` | Turns a live source on (`successfactors`, `peoplestrong`, `myhealth`, `hi5plus`). All off by default. |
| `MOCK_SOURCES_ENABLED`, `MOCK_SOURCE_TOKEN` | Serve AI-generated source-system endpoints from this app (see below). |
| `CHRO_ENV_FILE` | Alternative env file to load (the tests use this to stay hermetic). |
| `STUB_DATA_ENABLED` | Serve generated data for any source whose live integration is off (default on). |
| `CORS_ORIGINS` | JSON list of allowed frontend origins. |
| `SCHEDULER_ENABLED` | Run scheduled jobs in this process (default on). |

The API refuses to start if the database is behind the code; run `uv run alembic upgrade head`. Credentials for
connections are referenced by **environment-variable name** and are never stored or returned.

## How it fits together

**Scoring** (`app/scoring`, pure, no I/O): sub-KPI score = achievement ÷ target (inverted for lower-is-better KPIs); a pillar is the
weighted average of what is scoreable; missing, not-yet-due and no-source KPIs are excluded and the rest rescaled, never counted as
zero; Group achievement is the simple average of company achievements (Cost per Hire = total cost ÷ total hires). Thresholds, score
cap, minimum coverage for a status, pillar weights and year-to-date pro-rating are **admin-editable versioned rules**
(`/settings/scorecard`): draft → preview impact on real data → second admin approves.

**Data** (`app/ingestion`): each source returns raw counts; one module applies the formulas, so every stored value keeps its
numerator/denominator and lineage. A source is *live*, *stub* (AI- or deterministically generated), or *disabled*. Four KPIs are
entered by editors on the Manual inputs page. A KPI nothing can supply is labelled **No source**.

**AI-generated source systems** (`app/mock_sources`): until real tenants are connected, this app also serves endpoints shaped like
each source (OData, REST, flat, nested JSON; bearer token). Claude generates each company's profile once, stores it, and the
real live adapters read it over HTTP, so the whole ingestion path is exercised. Data carries an `X-Data-Origin` header into
lineage, and anything AI-made is flagged synthetic in the UI and reports. Set up with `uv run python -m scripts.setup_mock_sources`
(admin status/regenerate at `/mock-sources/admin/*`). Swapping in a real tenant is a base URL and mapping-file change.

**Capability registry** (`app/capabilities`): MCP servers (official SDK), OpenAPI APIs and built-in function tools are discovered
into versioned capabilities (draft → validated → published). An approved KPI mapping makes the platform pull that KPI through the
capability instead of a stub or live source.

**Approvals** (`app/approvals`): the only way to do anything consequential. Policy denies destructive and bulk actions, enforces
company scope, and the Copilot can only *propose*. Four-eyes: nobody approves their own request. Actions: send KPI reminder, create
or publish a report, publish a capability, publish a skill or agent, approve a KPI mapping, activate scorecard rules.

**Also:** alerts when a company turns red or ingestion fails · monthly leadership review as a resumable workflow with
AI commentary that is only kept if every number matches the computed results · immutable, hash-verified published reports ·
skills and agents (versioned, evaluated, approved) · document search (SQLite FTS5) · scheduler · pins and searchable sessions ·
per-user alert preferences, quiet hours and live push (SSE) · Copilot memory (per user, expiring, can be switched off or edited) ·
PDF export · editable KPI weights and targets (same draft → preview → approval flow) · admin-allowed registry capabilities
callable by the Copilot (read-only, published, group-wide).

## Testing

```bash
cd backend && uv run pytest -q && uv run ruff check app scripts tests migrations     # ~450 tests
cd frontend && pnpm exec tsc --noEmit && pnpm exec eslint src && pnpm build

# browser smoke test (drives the real UI against running servers on a COPY of the database)
cd backend && PYTHONPATH=. uv run --with playwright python ../e2e/smoke.py            # needs: uv run --with playwright python -m playwright install chromium
```

The Copilot and AI paths are tested with scripted fake clients; nothing in the test suite calls a real model (the suite ignores your `.env`). The browser smoke test is the opposite: it uses the real key against a copy of the database.

## Not built / known limits

- **SSO and login hardening** (pasted dev tokens only; deliberately skipped for now).
- **Golden test against the Excel prototype**: needs the workbook (only its image is in the repo). `tests/unit/test_prototype_conformance.py` covers the stated rules instead.
- Live source adapters are verified against the AI-generated endpoints and mocks, not real tenants.
- SQLite means one API instance; moving to Postgres is possible (the migrations render for it) but is untested.
