# AgenticChief API — build from repo root:
#   docker build -f backend/Dockerfile .
#
# Dokploy: Dockerfile Path = backend/Dockerfile, Docker Context Path = .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Layout matches local paths.py: REPO_ROOT/backend + REPO_ROOT/seed
WORKDIR /srv/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ .
COPY seed/ /srv/seed

RUN mkdir -p /data \
 && chmod +x /srv/backend/docker-entrypoint.sh

ENV DATABASE_URL=sqlite:////data/chro.db \
    VECTOR_STORE_PATH=/data/chroma \
    PYTHONUNBUFFERED=1

VOLUME /data
EXPOSE 8000

ENTRYPOINT ["/srv/backend/docker-entrypoint.sh"]
