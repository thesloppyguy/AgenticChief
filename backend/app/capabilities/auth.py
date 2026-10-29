"""Connection credentials are referenced by environment-variable NAME. The database never holds a secret
and no API response ever includes one."""
from __future__ import annotations

import base64
import os
import re

from .types import ConfigError

_ENV = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def validate_auth(auth: dict | None) -> dict:
    auth = auth or {"type": "none"}
    kind = auth.get("type")
    required = {"none": [], "bearer": ["token_env"], "header": ["header", "value_env"],
                "basic": ["user_env", "password_env"]}
    if kind not in required:
        raise ConfigError("auth.type must be none, bearer, header or basic")
    for k in required[kind]:
        if not auth.get(k):
            raise ConfigError(f"auth.{k} is required")
        if k.endswith("_env") and not _ENV.match(auth[k]):
            raise ConfigError(f"auth.{k} must be an environment variable NAME like MY_TOKEN")
    if kind == "header" and not re.match(r"^[A-Za-z0-9-]+$", auth["header"]):
        raise ConfigError("auth.header is not a valid header name")
    return {k: v for k, v in auth.items() if k in ("type", *required[kind])}


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise ConfigError(f"environment variable {name} is not set")  # the name only, never a value
    return v


def auth_headers(auth: dict | None) -> dict[str, str]:
    auth = auth or {"type": "none"}
    kind = auth.get("type", "none")
    if kind == "none":
        return {}
    if kind == "bearer":
        return {"Authorization": f"Bearer {_env(auth['token_env'])}"}
    if kind == "header":
        return {auth["header"]: _env(auth["value_env"])}
    if kind == "basic":
        raw = f"{_env(auth['user_env'])}:{_env(auth['password_env'])}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
    raise ConfigError("unknown auth type")
