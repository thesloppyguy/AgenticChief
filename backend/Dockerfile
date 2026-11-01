# AgenticChief API — build with context = backend/:
#   docker build -f backend/Dockerfile backend
#
# Dokploy:
#   Dockerfile Path      = Dockerfile
#   Docker Context Path  = backend
#   Domain               = chro.lokibots.ai
#   Env CORS_ORIGINS     = ["https://chro.lokibots.ai"]
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN mkdir -p /data \
 && chmod +x /app/docker-entrypoint.sh

ENV DATABASE_URL=sqlite:////data/chro.db \
    VECTOR_STORE_PATH=/data/chroma \
    SEED_ROOT=/app/seed \
    CORS_ORIGINS=["https://chro.lokibots.ai"] \
    PYTHONUNBUFFERED=1

VOLUME /data
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
