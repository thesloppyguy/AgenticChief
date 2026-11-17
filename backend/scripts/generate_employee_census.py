"""Generate SF-shaped employee census seed data (demo scale).

Usage:
  uv run python -m scripts.generate_employee_census
  uv run python -m scripts.generate_employee_census --per-ic 120 --seed lnt-v1 --write-json
  uv run python -m scripts.generate_employee_census --persist   # write into SQLite + MockCompanyData
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.migrate import upgrade_head
from app.db.session import SessionLocal
from app.fixtures.paths import GROUP_DIR
from app.org.companies import LNT_BY_CODE, LNT_CODES
from app.workforce.employee_sim.persist import census_fixture_dict, seed_census


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate SF-shaped employee census")
    ap.add_argument("--per-ic", type=int, default=None, help="active headcount target per IC")
    ap.add_argument("--seed", default="lnt-v1")
    ap.add_argument(
        "--write-json",
        action="store_true",
        help="write full census JSON under seed/lnt_group/workforce/census.json",
    )
    ap.add_argument(
        "--persist",
        action="store_true",
        help="persist census + MockCompanyData into the database",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional path for JSON output (defaults to workforce/census.json)",
    )
    a = ap.parse_args()

    assignments = [(c, LNT_BY_CODE[c][1]) for c in LNT_CODES]
    fixture = census_fixture_dict(assignments, per_ic=a.per_ic, seed=a.seed)

    if a.write_json or a.out:
        out = a.out or (GROUP_DIR / "workforce" / "census.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        # Strip nested census from companies for a lighter stub-compatible sibling if needed;
        # here we write the full artifact for offline inspection.
        out.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(f"wrote {out} ({out.stat().st_size} bytes)")

    if a.persist:
        upgrade_head()
        with SessionLocal() as db:
            summary = seed_census(
                db, assignments, per_ic=a.per_ic, seed=a.seed, clear=True
            )
        print(json.dumps({"persisted": summary["employees"]}, indent=2))
    else:
        counts = {
            code: len(payload["census"]["employees"])
            for code, payload in fixture["companies"].items()
        }
        print(json.dumps({"generated": counts, "seed": a.seed}, indent=2))


if __name__ == "__main__":
    main()
