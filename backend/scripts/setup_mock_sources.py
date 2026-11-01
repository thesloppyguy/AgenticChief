"""Point the live integrations at the AI-backed mock source systems.

Usage: uv run python -m scripts.setup_mock_sources [--base-url http://localhost:8000/api] [--write-env]

Always (re)writes integrations/mock/<source>.mapping.json from the endpoint catalog. With --write-env it also
adds the settings to backend/.env (a random bearer token is created once and reused). Existing values win.
"""
import argparse
import json
import secrets
from pathlib import Path

from app.ingestion.sources import SOURCE_KPIS
from app.mock_sources.catalog import mapping_for

ROOT = Path(__file__).resolve().parents[1]
MAPPINGS = ROOT / "integrations" / "mock"


def write_mappings() -> list[Path]:
    MAPPINGS.mkdir(parents=True, exist_ok=True)
    out = []
    for source in SOURCE_KPIS:
        p = MAPPINGS / f"{source}.mapping.json"
        p.write_text(json.dumps(mapping_for(source), indent=2, sort_keys=True) + "\n")
        out.append(p)
    return out


def env_block(base_url: str, token: str) -> dict[str, str]:
    env = {"MOCK_SOURCES_ENABLED": "true", "MOCK_SOURCE_TOKEN": token}
    for source in SOURCE_KPIS:
        pre = f"INTEGRATIONS__{source.upper()}__"
        env |= {pre + "ENABLED": "true", pre + "BASE_URL": base_url, pre + "AUTH": "bearer", pre + "TOKEN": token,
                pre + "MAPPING_FILE": f"./integrations/mock/{source}.mapping.json", pre + "TIMEOUT_S": "120"}
    return env


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000/api")
    ap.add_argument("--write-env", action="store_true")
    a = ap.parse_args()
    for p in write_mappings():
        print("wrote", p.relative_to(ROOT))
    if not a.write_env:
        print("\n(run again with --write-env to configure backend/.env)")
        return
    env_path = ROOT / ".env"
    text = env_path.read_text() if env_path.exists() else ""
    have = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in text.splitlines() if "=" in line and not line.startswith("#")}
    token = have.get("MOCK_SOURCE_TOKEN") or secrets.token_urlsafe(32)
    add = {k: v for k, v in env_block(a.base_url, token).items() if k not in have}
    if add:
        env_path.write_text(text.rstrip("\n") + "\n\n# AI-backed mock source systems (scripts.setup_mock_sources)\n"
                            + "\n".join(f"{k}={v}" for k, v in add.items()) + "\n")
    print(f"added {len(add)} setting(s) to .env ({len(env_block(a.base_url, token)) - len(add)} already present)")


if __name__ == "__main__":
    main()
