# Attrition sync — setup on a new machine

Pull IC attrition from CPI (`ICHRATTRITION`), store it locally in SQLite, and sync from the UI.

## Prerequisites

- Git, [uv](https://docs.astral.sh/uv/), Node 20+, [pnpm](https://pnpm.io/)
- Network access to the SAP CPI endpoint
- CPI Basic-auth username + password (do not commit these)

## 1. Clone and install

```bash
git clone <repo-url> AgenticChief
cd AgenticChief

# Backend
cd backend
uv sync
cp .env.example .env

# Frontend
cd ../frontend
pnpm install
```

## 2. Configure `.env` (backend)

Edit `backend/.env`:

```env
JWT_SECRET=change-me-to-a-random-string-of-at-least-32-characters

# Attrition CPI
INTEGRATIONS__ICHRATTRITION__ENABLED=true
INTEGRATIONS__ICHRATTRITION__BASE_URL=https://l550084-iflmap.hcisbp.ae1.hana.ondemand.com/http/ICHRATTRITION
INTEGRATIONS__ICHRATTRITION__AUTH=basic
INTEGRATIONS__ICHRATTRITION__USERNAME=<your-username>
INTEGRATIONS__ICHRATTRITION__PASSWORD=<your-password>
INTEGRATIONS__ICHRATTRITION__TIMEOUT_S=120
```

Optional: leave `ANTHROPIC_API_KEY` empty if you only need attrition sync (no Copilot).

## 3. Migrate DB and seed ICs

From `backend/`:

```bash
uv run alembic upgrade head
uv run python -m scripts.seed --reset
```

This creates/updates SQLite at `backend/data/chro.db` and upserts all ICs from `API.md` (PTD, TI, WETI, …).

## 4. Run the app

Terminal A — API:

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal B — UI:

```bash
cd frontend
pnpm dev
```

Open http://localhost:3000 and sign in as an **admin**.

## 5. Sync attrition data

### From the UI

1. Go to **Settings → Connectors**
2. Open **Attrition (ICHRATTRITION)**
3. Click **Sync attrition**
4. Wait for status: rows upserted + ICs ok/failed

A full roster sync hits every IC sequentially; with ~30 ICs this can take several minutes.

### From curl (API)

Get a JWT via login first (or use an existing admin token), then:

```bash
# Status
curl -s http://localhost:8000/api/attrition/status \
  -H "Authorization: Bearer <TOKEN>"

# Sync all ICs
curl -s -X POST http://localhost:8000/api/attrition/sync \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{}"

# Sync one IC only
curl -s -X POST http://localhost:8000/api/attrition/sync \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"ics\":[\"WETI\"]}"
```

### Raw CPI check (bypass the app)

```bash
curl --location --request GET \
  'https://l550084-iflmap.hcisbp.ae1.hana.ondemand.com/http/ICHRATTRITION' \
  --header 'Content-Type: application/xml' \
  --header 'Authorization: Basic <base64(username:password)>' \
  --data '<Trigger>
<IC>WETI</IC>
</Trigger>'
```

Expected shape: `{"MyzoneData":{"Employee":[ {...}, ... ]}}`.

## 6. Where data lands

| Store | Purpose |
| --- | --- |
| `attrition_employee` | Full mapped attrition fields + raw JSON |
| `attrition_sync_run` | Last sync status / errors |
| `employee` | Mirrored census rows for workforce metrics |
| `company` | IC codes; names refreshed from `ICDESCRIPTION` when present |

DB file: `backend/data/chro.db`.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| UI says “disabled” | `INTEGRATIONS__ICHRATTRITION__ENABLED=true` and restart uvicorn |
| 401 / auth errors | Username/password; regenerate Basic header |
| Timeouts | Raise `TIMEOUT_S` (e.g. 180); sync fewer ICs via `{"ics":["WETI"]}` |
| Empty rows for an IC | CPI returned `Employee: []` for that code — confirm the IC exists in CPI |
| Partial sync | Some ICs failed; see `last_sync.errors` on `/attrition/status` |

## Quick verify

```bash
cd backend
uv run pytest tests/attrition/ -q
```
