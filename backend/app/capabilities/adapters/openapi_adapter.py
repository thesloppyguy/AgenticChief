"""REST connections described by an OpenAPI 3 document: each operation becomes a tool."""
from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin

import httpx
import yaml

from ..types import DiscoveredTool, DiscoveryError, InvocationError
from ..urlguard import check_url

MAX_SPEC_BYTES = 5_000_000
MAX_OPS = 500
METHODS = ("get", "post", "put", "patch", "delete")
RISK_BY_METHOD = {"get": "read", "post": "internal_write", "put": "internal_write",
                  "patch": "internal_write", "delete": "destructive"}


def load_spec(text_or_dict: str | dict) -> dict:
    if isinstance(text_or_dict, dict):
        return text_or_dict
    if len(text_or_dict) > MAX_SPEC_BYTES:
        raise DiscoveryError("OpenAPI document is too large")
    try:
        spec = yaml.safe_load(text_or_dict)  # YAML is a superset of JSON
    except yaml.YAMLError as e:
        raise DiscoveryError("OpenAPI document is not valid JSON or YAML") from e
    if not isinstance(spec, dict) or "paths" not in spec:
        raise DiscoveryError("not an OpenAPI document (no 'paths')")
    return spec


def fetch_spec(url: str, headers: dict, timeout_s: float = 30) -> dict:
    check_url(url)
    try:
        r = httpx.get(url, headers=headers, timeout=timeout_s, follow_redirects=False)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise DiscoveryError(f"could not fetch the OpenAPI document ({type(e).__name__})") from e
    return load_spec(r.text)


def _deref(node, spec: dict, depth: int = 0):
    """Inline local $refs (#/components/...). Anything deeper than 8 levels, or a cycle, becomes {}."""
    if depth > 8:
        return {}
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/"):
            target = spec
            for part in node["$ref"][2:].split("/"):
                target = target.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(target, dict) else {}
            return _deref(target, spec, depth + 1)
        return {k: _deref(v, spec, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_deref(v, spec, depth + 1) for v in node]
    return node


def _name(op: dict, method: str, path: str) -> str:
    if op.get("operationId"):
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", op["operationId"]).strip("_")
    else:  # e.g. "delete /notes/{id}" -> "delete_notes_id"
        name = re.sub(r"[^A-Za-z0-9]+", "_", f"{method} {path}").strip("_")
    return name[:100] or f"{method}_op"


def _json_schema_of(content: dict | None) -> dict | None:
    for media, body in (content or {}).items():
        if "json" in media and isinstance(body, dict) and body.get("schema"):
            return body["schema"]
    return None


def server_url(spec: dict, spec_url: str | None = None) -> str | None:
    servers = spec.get("servers") or []
    if not servers or not servers[0].get("url"):
        return None
    url = servers[0]["url"]
    return urljoin(spec_url, url) if spec_url and not re.match(r"^https?://", url) else url


def parse(spec: dict) -> list[DiscoveredTool]:
    tools: list[DiscoveredTool] = []
    seen: set[str] = set()
    for path, item in (spec.get("paths") or {}).items():
        item = _deref(item, spec)
        shared = item.get("parameters", [])
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            if len(tools) >= MAX_OPS:
                raise DiscoveryError(f"more than {MAX_OPS} operations: import a narrower spec")
            name = _name(op, method, path)
            if name in seen:
                name = f"{name}_{method}"
            seen.add(name)
            props, required, params = {}, [], []
            for p in [*shared, *op.get("parameters", [])]:
                if p.get("in") not in ("path", "query") or not p.get("name"):
                    continue  # header/cookie parameters are not exposed
                props[p["name"]] = {**(p.get("schema") or {"type": "string"}),
                                    **({"description": p["description"]} if p.get("description") else {})}
                params.append({"name": p["name"], "in": p["in"]})
                if p.get("required") or p["in"] == "path":
                    required.append(p["name"])
            body = _json_schema_of((op.get("requestBody") or {}).get("content"))
            if body is not None:
                props["body"] = body
                if (op.get("requestBody") or {}).get("required"):
                    required.append("body")
            responses = op.get("responses") or {}
            out = next((_json_schema_of((responses.get(c) or {}).get("content"))
                        for c in ("200", "201", "2XX", "default") if c in responses), None)
            tools.append(DiscoveredTool(
                name=name,
                description=(op.get("description") or op.get("summary") or "").strip(),
                input_schema={"type": "object", "properties": props, "required": sorted(set(required))},
                output_schema=out,
                implementation={"type": "http", "method": method.upper(), "path": path, "params": params,
                                "has_body": body is not None},
                risk=RISK_BY_METHOD[method]))
    return tools


def call(config: dict, headers: dict, impl: dict, args: dict) -> dict:
    base = (config.get("server_url") or "").rstrip("/")
    path = impl["path"]
    for p in impl["params"]:
        if p["in"] == "path":
            path = path.replace("{" + p["name"] + "}", quote(str(args[p["name"]]), safe=""))
    query = {p["name"]: args[p["name"]] for p in impl["params"] if p["in"] == "query" and p["name"] in args}
    url = base + path
    check_url(url)
    try:
        r = httpx.request(impl["method"], url, params=query, headers={"Accept": "application/json", **headers},
                          json=args.get("body") if impl.get("has_body") else None,
                          timeout=config.get("timeout_s", 30), follow_redirects=False)
    except httpx.HTTPError as e:
        raise InvocationError(f"HTTP call failed ({type(e).__name__})") from e
    if r.status_code >= 300:
        raise InvocationError(f"HTTP {r.status_code}")
    try:
        data = r.json()
    except json.JSONDecodeError:
        return {"text": r.text[:2000]}
    return data if isinstance(data, dict) else {"items": data} if isinstance(data, list) else {"value": data}
