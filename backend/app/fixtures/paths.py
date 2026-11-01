from __future__ import annotations

import os
from pathlib import Path

# backend/seed — co-located so Docker context=backend includes fixtures
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]

_env = os.environ.get("SEED_ROOT")
if _env:
    SEED_ROOT = Path(_env)
elif (BACKEND_ROOT / "seed").is_dir():
    SEED_ROOT = BACKEND_ROOT / "seed"
else:
    # legacy repo-root seed/ (older checkouts)
    SEED_ROOT = REPO_ROOT / "seed"

GROUP_DIR = SEED_ROOT / "lnt_group"
COMPANIES_DIR = SEED_ROOT / "companies"
