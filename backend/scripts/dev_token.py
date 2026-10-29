"""Print a dev JWT. Usage: uv run python -m scripts.dev_token admin|editor|viewer [company_id ...]"""
import sys

from app.core.security import Role, make_token

role = Role(sys.argv[1])
companies = [int(c) for c in sys.argv[2:]] or None
print(make_token(f"dev-{role.value}", role, companies))
