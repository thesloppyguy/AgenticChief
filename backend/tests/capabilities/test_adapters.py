import json
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS

import httpx
import pytest

from app.capabilities import auth as auth_mod
from app.capabilities.adapters import function_adapter, mcp_adapter, openapi_adapter
from app.capabilities.invoke import invoke, validate_args
from app.capabilities.types import ConfigError, DiscoveryError, InvocationError
from app.capabilities.urlguard import check_url
from tests.capabilities.conftest import MCP_URL, SPEC

# --- URL guard and credentials ---

@pytest.mark.parametrize("url", ["http://localhost:8080/x", "https://127.0.0.1/mcp", "http://[::1]:9/mcp",
                                 "http://10.0.0.5/api", "http://192.168.1.20:8443/mcp"])
def test_internal_addresses_are_allowed(url):
    check_url(url)  # internal HR systems live on private networks; this must not raise


@pytest.mark.parametrize("url,why", [
    ("ftp://localhost/x", "http"), ("file:///etc/passwd", "http"), ("http:///nohost", "http"),
    ("http://user:pw@localhost/x", "credentials"), ("http://169.254.169.254/latest/meta-data", "not allowed"),
    ("http://[fe80::1]/x", "not allowed"), ("http://0.0.0.0/x", "not allowed"),
    ("http://[::ffff:169.254.169.254]/x", "not allowed"),               # metadata address wrapped in IPv6
    ("http://no-such-host.invalid/x", "resolve"),
])
def test_unsafe_urls_are_refused(url, why):
    with pytest.raises(ConfigError, match=why):
        check_url(url)


def test_auth_config_holds_env_names_never_values(monkeypatch):
    assert auth_mod.validate_auth(None) == {"type": "none"}
    clean = auth_mod.validate_auth({"type": "bearer", "token_env": "HR_TOKEN", "token": "s3cret", "extra": 1})
    assert clean == {"type": "bearer", "token_env": "HR_TOKEN"}                  # a pasted secret is dropped
    for bad in ({"type": "bearer"}, {"type": "bearer", "token_env": "lower case"}, {"type": "oauth"},
                {"type": "header", "header": "bad header", "value_env": "X"}):
        with pytest.raises(ConfigError):
            auth_mod.validate_auth(bad)
    monkeypatch.setenv("HR_TOKEN", "abc")
    assert auth_mod.auth_headers(clean) == {"Authorization": "Bearer abc"}
    monkeypatch.setenv("KEY", "k")
    assert auth_mod.auth_headers({"type": "header", "header": "X-Api-Key", "value_env": "KEY"}) == {"X-Api-Key": "k"}
    monkeypatch.delenv("HR_TOKEN")
    with pytest.raises(ConfigError) as e:
        auth_mod.auth_headers(clean)
    assert "HR_TOKEN" in str(e.value) and "abc" not in str(e.value)


# --- OpenAPI ---

def test_openapi_operations_become_tools_with_schemas_and_risk():
    tools = {t.name: t for t in openapi_adapter.parse(SPEC)}
    assert set(tools) == {"getPli", "addNote", "delete_notes_id"}                # readable names when there is no operationId
    pli = tools["getPli"]
    assert pli.risk == "read" and pli.description == "PLI assessment counts."
    assert pli.input_schema["properties"].keys() == {"code", "period"}          # header parameter not exposed
    assert pli.input_schema["required"] == ["code", "period"]
    assert pli.output_schema["properties"].keys() == {"completed", "total"}       # $ref inlined
    assert pli.implementation == {"type": "http", "method": "GET", "path": "/companies/{code}/pli",
                                  "params": [{"name": "code", "in": "path"}, {"name": "period", "in": "query"}],
                                  "has_body": False}
    note = tools["addNote"]
    assert note.risk == "internal_write" and note.input_schema["required"] == ["body"]
    assert note.input_schema["properties"]["body"]["required"] == ["text"]
    assert next(t for t in tools.values() if t.implementation["method"] == "DELETE").risk == "destructive"


def test_openapi_yaml_servers_and_bad_documents():
    doc = "openapi: 3.0.0\nservers: [{url: /api}]\npaths: {/a: {get: {operationId: a}}}\n"
    spec = openapi_adapter.load_spec(doc)
    assert openapi_adapter.server_url(spec, "https://hr.example.com/docs/openapi.yaml") == "https://hr.example.com/api"
    assert openapi_adapter.server_url({"paths": {}}) is None
    for bad in ("not: [valid", "just text", "{}"):
        with pytest.raises(DiscoveryError):
            openapi_adapter.load_spec(bad)


def test_openapi_circular_refs_do_not_hang():
    spec = {"paths": {"/n": {"get": {"operationId": "n", "responses": {"200": {"content": {"application/json": {
        "schema": {"$ref": "#/components/schemas/Node"}}}}}}}},
        "components": {"schemas": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/components/schemas/Node"}}}}}}
    assert openapi_adapter.parse(spec)[0].output_schema["type"] == "object"


def test_openapi_call_builds_the_request_and_normalizes_the_response(monkeypatch):
    seen = {}

    def fake(method, url, **kw):
        seen.update(method=method, url=url, **kw)
        return httpx.Response(200, json=[1, 2], request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake)
    impl = {"method": "GET", "path": "/companies/{code}/pli", "has_body": False,
            "params": [{"name": "code", "in": "path"}, {"name": "period", "in": "query"}]}
    out = openapi_adapter.call({"server_url": "http://localhost:8099/v1", "timeout_s": 5}, {"Authorization": "Bearer t"},
                               impl, {"code": "IC 1/x", "period": "2026-10"})
    assert out == {"items": [1, 2]}
    assert seen["url"] == "http://localhost:8099/v1/companies/IC%201%2Fx/pli"      # path value is escaped
    assert seen["params"] == {"period": "2026-10"} and seen["headers"]["Authorization"] == "Bearer t"
    assert seen["follow_redirects"] is False                                       # no redirect-based SSRF
    monkeypatch.setattr(httpx, "request", lambda m, u, **kw: httpx.Response(500, request=httpx.Request(m, u)))
    with pytest.raises(InvocationError, match="HTTP 500"):
        openapi_adapter.call({"server_url": "http://localhost:8099", "timeout_s": 5}, {}, impl, {"code": "a", "period": "p"})


# --- function tools ---

def test_function_tools_are_discoverable_and_callable(client):
    from app.db.session import get_db
    from app.main import app
    db = next(app.dependency_overrides[get_db]())
    tools = {t.name: t for t in function_adapter.discover()}
    assert set(tools) == {"list_companies", "group_score"} and all(t.risk == "read" for t in tools.values())
    assert tools["group_score"].input_schema["required"] == ["period"]
    out = function_adapter.call(db, "list_companies", {})
    assert [c["code"] for c in out["companies"]] == ["IC1", "IC2", "IC3"]
    with pytest.raises(InvocationError):
        function_adapter.call(db, "rm_rf", {})
    conn = NS(config={})
    assert invoke(db, conn, {"type": "function", "ref": "group_score"}, tools["group_score"].input_schema,
                  {"period": "2026-10"})["companies_in_scope"] == 3


def test_arguments_are_validated_against_the_schema_before_any_call():
    schema = {"type": "object", "properties": {"period": {"type": "string"}, "n": {"type": "integer"}},
              "required": ["period"]}
    validate_args(schema, {"period": "2026-10", "n": 1})
    for bad in ({}, {"period": 5}, {"period": "x", "n": "many"}):
        with pytest.raises(InvocationError):
            validate_args(schema, bad)


# --- MCP ---

def test_mcp_discovery_classifies_risk_and_keeps_schemas(mcp_server):
    tools = {t.name: t for t in mcp_adapter.discover({"url": MCP_URL}, {})}
    assert tools["kra_stats"].risk == "read" and tools["notify_leads"].risk == "destructive"  # untagged = cautious
    assert tools["kra_stats"].output_schema["properties"].keys() == {"submitted", "eligible"}
    assert tools["kra_stats"].implementation == {"type": "mcp", "tool": "kra_stats"}


def test_mcp_call_returns_structured_output_and_reports_tool_errors(mcp_server):
    out = mcp_adapter.call({"url": MCP_URL}, {}, "kra_stats", {"company_code": "IC1", "period": "2026-10"})
    assert out == {"submitted": 90, "eligible": 100}
    with pytest.raises(InvocationError, match="tool reported an error"):
        mcp_adapter.call({"url": MCP_URL}, {}, "kra_stats", {"nonsense": 1})
    mcp_server["down"] = True
    with pytest.raises(InvocationError, match="ConnectionError") as e:
        mcp_adapter.call({"url": MCP_URL}, {}, "kra_stats", {})
    assert "simulated outage" not in str(e.value)                                  # upstream text is not echoed
    with pytest.raises(DiscoveryError, match="ConnectionError"):
        mcp_adapter.discover({"url": MCP_URL}, {})


def test_mcp_discovery_follows_pagination(monkeypatch):
    pages = {None: (["a", "b"], "p2"), "p2": (["c"], None)}

    class FakeClient:
        async def list_tools(self, *, cursor=None):
            names, nxt = pages[cursor]
            return NS(tools=[NS(name=n, description=n, title=None, input_schema={"type": "object"},
                                output_schema=None, annotations=None) for n in names], next_cursor=nxt)

    @asynccontextmanager
    async def opener(cfg, hdr):
        yield FakeClient()

    monkeypatch.setattr(mcp_adapter, "_open", opener)
    assert [t.name for t in mcp_adapter.discover({"url": MCP_URL}, {})] == ["a", "b", "c"]


def test_mcp_over_real_http_sends_the_bearer_token_and_a_wrong_one_fails(http_mcp_server, monkeypatch):
    cfg = {"url": http_mcp_server["url"], "timeout_s": 10}
    tools = mcp_adapter.discover(cfg, {"Authorization": "Bearer s3cret-token"})
    assert {t.name for t in tools} == {"kra_stats", "notify_leads"}
    assert mcp_adapter.call(cfg, {"Authorization": "Bearer s3cret-token"}, "kra_stats",
                            {"company_code": "IC1", "period": "2026-10"}) == {"submitted": 90, "eligible": 100}
    assert "Bearer s3cret-token" in http_mcp_server["seen"]
    with pytest.raises(DiscoveryError):
        mcp_adapter.discover(cfg, {"Authorization": "Bearer wrong"})
    with pytest.raises(DiscoveryError):
        mcp_adapter.discover(cfg, {})
    assert json.dumps(http_mcp_server["seen"]).count("s3cret-token") >= 1
