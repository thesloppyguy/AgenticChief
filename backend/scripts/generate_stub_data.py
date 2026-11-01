"""Generate the stub-data fixture for the 5 L&T ICs.

Usage:
  uv run python -m scripts.generate_stub_data            # deterministic (default)
  uv run python -m scripts.generate_stub_data --ai       # Claude (costs tokens)
"""
import argparse

from app.core.config import settings
from app.ingestion.ai_generator import write_fixture
from scripts.seed_integrations import lnt_fixture

ap = argparse.ArgumentParser()
ap.add_argument("--ai", action="store_true")
ap.add_argument("--out", default=settings.stub_data_path)
a = ap.parse_args()

fixture = lnt_fixture(ai=a.ai)
write_fixture(a.out, fixture)
m = fixture["meta"]
print(
    f"wrote {a.out}: {m['ai_generated']}/{m['count']} AI-generated, "
    f"{m['count'] - m['ai_generated']} deterministic"
)
for n in m["notes"]:
    print("  note:", n)
