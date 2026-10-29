"""Tests must be hermetic: they never read a developer's .env and never reach a real model.

This runs before any test module imports the app, so `settings` is built from defaults. (Without it, a
developer who has configured live integrations and an API key would run every test against that setup,
and some would spend real money.)
"""
import os

os.environ["CHRO_ENV_FILE"] = os.devnull
for var in [v for v in os.environ if v.startswith(("INTEGRATIONS__", "MOCK_SOURCE", "STUB_DATA", "ANTHROPIC_API_KEY", "DATABASE_URL"))]:
    os.environ.pop(var)
