"""Call a capability. Arguments are validated against the version's input schema first."""
from __future__ import annotations

from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from app.db.models import Connection

from .adapters import function_adapter, mcp_adapter, openapi_adapter
from .auth import auth_headers
from .types import InvocationError


def validate_args(schema: dict, args: dict) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(args), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        where = ".".join(str(p) for p in e.path) or "arguments"
        raise InvocationError(f"invalid {where}: {e.message[:120]}")


def invoke(db: Session, conn: Connection, impl: dict, input_schema: dict, args: dict) -> dict:
    validate_args(input_schema, args)
    kind = impl.get("type")
    if kind == "function":
        return function_adapter.call(db, impl["ref"], args)
    headers = auth_headers(conn.config.get("auth"))
    if kind == "mcp":
        return mcp_adapter.call(conn.config, headers, impl["tool"], args)
    if kind == "http":
        return openapi_adapter.call(conn.config, headers, impl, args)
    raise InvocationError("unknown implementation type")
