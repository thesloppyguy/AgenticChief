# Docker / Dokploy

Canonical images:

| Service | Dockerfile | Build context |
|---|---|---|
| API | `backend/Dockerfile` | repo root (`.`) |
| Web | `frontend/Dockerfile` | `frontend/` |

```bash
# from repo root
docker compose -f docker/docker-compose.yml up --build
```

## Dokploy (two Applications)

**API**

- Build type: Dockerfile
- Dockerfile path: `backend/Dockerfile`
- Docker context: `.`
- Port: `8000`
- Mount a persistent volume at `/data`
- Env: `JWT_SECRET`, `ANTHROPIC_API_KEY`, `CORS_ORIGINS=["https://<web-domain>"]`, optional `SEED_ON_START=auto|true|false`

On first boot the entrypoint runs migrations and `scripts.seed_lnt --reset`, then writes `/data/.lnt_seeded`. Set `SEED_ON_START=true` to force a re-seed (wipes demo org data).

**Web**

- Build type: Dockerfile
- Dockerfile path: `Dockerfile` (context `frontend`) or `frontend/Dockerfile` with context `frontend`
- Docker context: `frontend`
- Port: `3000`
- Build-time arg: `NEXT_PUBLIC_API_URL=https://<api-domain>`

## Dokploy (Compose)

Compose path: `docker/docker-compose.yml`. Uncomment `dokploy-network` + Traefik labels and set your hosts. Provide `JWT_SECRET`, `ANTHROPIC_API_KEY`, `CORS_ORIGINS`, and `NEXT_PUBLIC_API_URL` in the environment.
