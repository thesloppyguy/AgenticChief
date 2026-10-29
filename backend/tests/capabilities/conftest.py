import socket
import threading
import time
import warnings

import pytest
import uvicorn
from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from app.capabilities.adapters import mcp_adapter
from tests.api.conftest import client  # noqa: F401  (re-exported fixture)

warnings.filterwarnings("ignore", message=".*model_(computed_)?fields.*")


class KraStats(BaseModel):
    submitted: int
    eligible: int


class MidTerm(BaseModel):
    completed: int
    eligible: int


def make_server(version: int = 1, wording: str = "KRA submission counts for a company and period.") -> MCPServer:
    """v1: kra_stats (read) + notify_leads (untagged -> treated as destructive).
    v2: kra_stats gains a parameter, notify_leads is gone, mid_term_stats appears."""
    srv = MCPServer("hr")
    ro = ToolAnnotations(read_only_hint=True)
    if version == 1:
        @srv.tool(name="kra_stats", description=wording, annotations=ro)
        def kra_stats(company_code: str, period: str) -> KraStats:
            return KraStats(submitted=90, eligible=100)

        @srv.tool(name="notify_leads", description="Message every HR lead.")
        def notify_leads(message: str) -> dict:
            return {"sent": 3}
    else:
        @srv.tool(name="kra_stats", description=wording, annotations=ro)
        def kra_stats2(company_code: str, period: str, include_contractors: bool = False) -> KraStats:
            return KraStats(submitted=90, eligible=100)

        @srv.tool(name="mid_term_stats", description="Mid-term review completion counts for a company and period.",
                  annotations=ro)
        def mid_term_stats(company_code: str, period: str) -> MidTerm:
            return MidTerm(completed=40, eligible=50)
    return srv


@pytest.fixture()
def mcp_server(monkeypatch):
    """Swap the network for an in-process MCP server. state['server'] can be replaced mid-test."""
    state = {"server": make_server(1), "down": False, "calls": []}

    def opener(config, headers):
        if state["down"]:
            raise ConnectionError("simulated outage")
        state["calls"].append(dict(headers))
        return Client(state["server"])

    monkeypatch.setattr(mcp_adapter, "_open", opener)
    return state


MCP_URL = "http://localhost:9/mcp"  # never contacted when the in-process server is patched in

SPEC = {
    "openapi": "3.0.3", "info": {"title": "People API", "version": "1"},
    "servers": [{"url": "http://localhost:8099/v1"}],
    "paths": {
        "/companies/{code}/pli": {
            "parameters": [{"name": "code", "in": "path", "required": True, "schema": {"type": "string"}}],
            "get": {"operationId": "getPli", "summary": "PLI completion", "description": "PLI assessment counts.",
                    "parameters": [{"name": "period", "in": "query", "required": True, "schema": {"type": "string"}},
                                   {"name": "X-Trace", "in": "header", "schema": {"type": "string"}}],
                    "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pli"}}}}}},
        },
        "/notes": {"post": {"operationId": "addNote", "summary": "Add a note",
                            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                                "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}},
                            "responses": {"201": {"description": "created"}}}},
        "/notes/{id}": {"delete": {"summary": "Delete a note", "parameters": [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "responses": {"204": {"description": "gone"}}}},
    },
    "components": {"schemas": {"Pli": {"type": "object", "properties": {
        "completed": {"type": "integer"}, "total": {"type": "integer"}}, "required": ["completed", "total"]}}},
}


@pytest.fixture()
def http_mcp_server():
    """A real MCP server on a real port, behind a bearer-token check (Streamable HTTP)."""
    seen: list[str | None] = []
    inner = make_server(1).streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope["headers"]).get(b"authorization", b"").decode()
            seen.append(auth or None)
            if auth != "Bearer s3cret-token":
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await inner(scope, receive, send)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield {"url": f"http://127.0.0.1:{port}/mcp", "seen": seen}
    server.should_exit = True
    t.join(timeout=5)
