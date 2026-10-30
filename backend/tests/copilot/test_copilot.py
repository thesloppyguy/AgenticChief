import json
from types import SimpleNamespace as NS

from app.api.copilot import get_anthropic
from app.copilot.tools import TOOLS
from app.core.security import Role
from app.main import app
from tests.api.conftest import auth, client  # noqa: F401


class FakeStream:
    def __init__(self, msg, text):
        self._msg, self._text = msg, text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def text_stream(self):
        async def gen():
            if self._text:
                yield self._text
        return gen()

    async def get_final_message(self):
        return self._msg


class FakeClient:
    """First turn asks for a tool; second turn answers using its result."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            block = NS(type="tool_use", id="t1", name="get_group_score", input={"period": "2026-10"},
                       model_dump=lambda: {"type": "tool_use", "id": "t1", "name": "get_group_score",
                                           "input": {"period": "2026-10"}})
            return FakeStream(NS(stop_reason="tool_use", content=[block]), "")
        return FakeStream(NS(stop_reason="end_turn", content=[]), "Group is unscored.")


def test_tools_sorted_and_cached_prefix_stable():
    names = [t["name"] for t in TOOLS]
    assert names == sorted(names)


def test_chat_runs_tool_and_persists(client):
    fake = FakeClient()
    app.dependency_overrides[get_anthropic] = lambda: fake
    h = auth(Role.VIEWER, [1])
    r = client.post("/copilot/chat", json={"message": "group score?", "period": "2026-10"}, headers=h)
    events = [json.loads(l[5:]) for l in r.text.splitlines() if l.startswith("data:")]
    assert [e["type"] for e in events] == ["tool", "chunk", "done"]
    # tool result fed back to the model came from the scoring service, scoped to company 1
    tool_result = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert tool_result["scope"] == "restricted" and tool_result["companies_in_scope"] == 1
    sid = events[-1]["session_id"]
    msgs = client.get(f"/copilot/sessions/{sid}", headers=h).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    # another user cannot read it
    other = {"Authorization": auth(Role.VIEWER)["Authorization"].replace("u1", "u2")}
    from app.core.security import make_token
    assert client.get(f"/copilot/sessions/{sid}",
                      headers={"Authorization": f"Bearer {make_token('u2', Role.VIEWER)}"}).status_code == 404


def test_tools_run_off_the_event_loop(client, monkeypatch):
    """A slow tool (a scorecard over 88 companies) must not stall every other request."""
    import threading

    import app.copilot.orchestrator as orch

    seen = {}

    def spy(db, who, name, args, session_id=None, **kw):
        seen["thread"] = threading.current_thread().name
        return {"ok": True}

    monkeypatch.setattr(orch, "run_tool", spy)
    fake = FakeClient()
    app.dependency_overrides[get_anthropic] = lambda: fake
    client.post("/copilot/chat", json={"message": "x", "period": "2026-10"}, headers=auth(Role.VIEWER, [1]))
    assert seen["thread"] != "MainThread" and seen["thread"] != threading.main_thread().name
