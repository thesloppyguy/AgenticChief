#!/bin/sh
# Migrate, seed on first boot, then serve. Persists SQLite + Chroma under /data.
set -eu

mkdir -p /data

echo "[api] alembic upgrade head"
uv run alembic upgrade head

seed_mode="${SEED_ON_START:-auto}"
case "$seed_mode" in
  1|true|TRUE|yes|YES)
    echo "[api] SEED_ON_START=$seed_mode -> seeding L&T demo (--reset)"
    uv run python -m scripts.seed_lnt --reset
    touch /data/.lnt_seeded
    ;;
  0|false|FALSE|no|NO)
    echo "[api] SEED_ON_START=$seed_mode -> skip seed"
    ;;
  auto|*)
    if [ ! -f /data/.lnt_seeded ]; then
      echo "[api] first boot -> seeding L&T demo (--reset)"
      uv run python -m scripts.seed_lnt --reset
      touch /data/.lnt_seeded
    else
      echo "[api] /data/.lnt_seeded present -> skip seed"
    fi
    ;;
esac

echo "[api] uvicorn on 0.0.0.0:8000"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
