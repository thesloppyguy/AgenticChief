# Docker / Dokploy

Both services use **`https://chro.lokibots.ai`**.

| Service | Dockerfile | Build context | Domain |
|---|---|---|---|
| API | `backend/Dockerfile` | `backend/` | `chro.lokibots.ai` |
| Web | `frontend/Dockerfile` | `frontend/` | `chro.lokibots.ai` |

```bash
# from repo root
docker compose -f docker/docker-compose.yml up --build
```

## Dokploy (two Applications)

**API**

| Field | Value |
|---|---|
| Dockerfile Path | `Dockerfile` |
| Docker Context Path | `backend` |
| Port | `8000` |
| Domain | `chro.lokibots.ai` |

- Volume: `/data`
- Env:
  - `JWT_SECRET`
  - `ANTHROPIC_API_KEY`
  - `CORS_ORIGINS=https://chro.lokibots.ai` (optional; already the app default)
  - optional `SEED_ON_START=auto|true|false`

If web and API share the host, set the API app **path** to `/api` (strip prefix) in Dokploy, and web build arg `NEXT_PUBLIC_API_URL=https://chro.lokibots.ai/api`.

**Web**

| Field | Value |
|---|---|
| Dockerfile Path | `Dockerfile` |
| Docker Context Path | `frontend` |
| Port | `3000` |
| Domain | `chro.lokibots.ai` |
| Build arg | `NEXT_PUBLIC_API_URL=https://chro.lokibots.ai` |

## DNS

Point `chro.lokibots.ai` (A/AAAA or CNAME) at the Dokploy host.
