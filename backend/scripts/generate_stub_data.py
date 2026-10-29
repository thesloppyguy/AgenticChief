"""Generate the AI stub-data fixture with Claude.

Usage: uv run python -m scripts.generate_stub_data [--count 88] [--batch-size 8] [--out stub_data/stub_company_data.json]

Needs Anthropic credentials (ANTHROPIC_API_KEY, or `ant auth login`). Costs real tokens: about
count/batch-size requests. Companies the model gets wrong fall back to the deterministic generator and
are marked origin=synthetic_fallback in the fixture.
"""
import argparse

import anthropic

from app.core.config import settings
from app.ingestion.ai_generator import generate_fixture, write_fixture

ap = argparse.ArgumentParser()
ap.add_argument("--count", type=int, default=88)
ap.add_argument("--batch-size", type=int, default=8)
ap.add_argument("--out", default=settings.stub_data_path)
ap.add_argument("--model", default=settings.stub_generator_model)
a = ap.parse_args()

client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key \
    else anthropic.Anthropic()
codes = [f"IC{i:03d}" for i in range(1, a.count + 1)]
fixture = generate_fixture(client, a.model, codes, a.batch_size)
write_fixture(a.out, fixture)
m = fixture["meta"]
print(f"wrote {a.out}: {m['ai_generated']}/{m['count']} AI-generated, "
      f"{m['count'] - m['ai_generated']} deterministic fallback")
for n in m["notes"]:
    print("  note:", n)
