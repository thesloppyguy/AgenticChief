from types import SimpleNamespace as NS


class Stream:
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


class ScriptedClient:
    """Plays back a script: ('tool', name, input) asks for a tool, ('text', words) answers. Records every call."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []
        self.messages = self

    def stream(self, **kw):
        self.calls.append(kw)
        step = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if step[0] == "tool":
            _, name, args = step
            block = NS(type="tool_use", id=f"t{len(self.calls)}", name=name, input=args,
                       model_dump=lambda n=name, a=args, i=len(self.calls): {"type": "tool_use", "id": f"t{i}", "name": n, "input": a})
            return Stream(NS(stop_reason="tool_use", content=[block]), "")
        return Stream(NS(stop_reason="end_turn", content=[]), step[1])
