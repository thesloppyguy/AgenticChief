"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { api } from "@/lib/api";
import { streamChat } from "@/lib/chat";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const DEFAULT_AGENT = "default";  // Select values cannot be empty; maps to no agent_key

interface Msg { role: "user" | "assistant"; content: string; tools?: string[] }
interface Sess { id: number; title: string }
interface AgentRow { key: string; name: string; description: string }

function Chat() {
  const [period] = usePeriod();
  const params = useSearchParams();
  const sessions = useApi<Sess[]>("/copilot/sessions");
  const agents = useApi<AgentRow[]>("/agents");
  const [sid, setSid] = useState<number | null>(null);
  const [agent, setAgent] = useState(params.get("agent") ?? "");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });  // no `return`: an effect must only return a cleanup function
  }, [msgs]);

  async function open(id: number) {
    setSid(id);
    setMsgs((await api<{ messages: Msg[] }>(`/copilot/sessions/${id}`)).messages);
  }
  const fromUrl = params.get("session");
  useEffect(() => {
    if (!fromUrl) return;
    let live = true;  // state is set only after the request resolves, and not at all if we navigated away
    api<{ messages: Msg[] }>(`/copilot/sessions/${fromUrl}`)
      .then((r) => { if (live) { setSid(Number(fromUrl)); setMsgs(r.messages); } })
      .catch(() => live && setMsgs([{ role: "assistant", content: "That session could not be opened." }]));
    return () => { live = false; };
  }, [fromUrl]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "", tools: [] }]);
    const patch = (fn: (m: Msg) => Msg) => setMsgs((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));
    await streamChat({ message: text, session_id: sid, period, ...(agent ? { agent_key: agent } : {}) }, {
      onChunk: (c) => patch((m) => ({ ...m, content: m.content + c })),
      onTool: (n) => patch((m) => ({ ...m, tools: [...(m.tools ?? []), n] })),
      onError: (msg) => patch((m) => ({ ...m, content: msg })),
      onDone: (id) => { setSid(id); sessions.reload(); },
    });
    setBusy(false);
  }

  const agentItems = [{ value: DEFAULT_AGENT, label: "Copilot (default)" }, ...(agents.data ?? []).map((a) => ({ value: a.key, label: a.name }))];
  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      <aside className="w-56 shrink-0 overflow-y-auto rounded-lg border bg-card p-3 text-sm">
        <Button className="mb-2 w-full" onClick={() => { setSid(null); setMsgs([]); }}>New session</Button>
        <ul>
          {sessions.data?.map((s) => (
            <li key={s.id}><Button variant="ghost" onClick={() => open(s.id)} className={cn("w-full justify-start truncate text-left font-normal", s.id === sid && "bg-muted")}><span className="truncate">{s.title}</span></Button></li>
          ))}
        </ul>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col rounded-lg border bg-card">
        <div className="flex items-center gap-2 border-b px-4 py-2 text-sm">
          <Label htmlFor="agent" className="text-muted-foreground">Agent</Label>
          <Select items={agentItems} value={agent || DEFAULT_AGENT} onValueChange={(v) => v != null && setAgent(v === DEFAULT_AGENT ? "" : v)}>
            <SelectTrigger id="agent"><SelectValue /></SelectTrigger>
            <SelectContent>
              {agentItems.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {agent && <span className="text-xs text-muted-foreground">{agents.data?.find((a) => a.key === agent)?.description}</span>}
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {msgs.length === 0 && (
            <p className="text-sm text-muted-foreground">Try: “What is the current Group HR score?”, “Which pillars need attention?”, “How is top talent retention calculated?”</p>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <div className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-left text-sm ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                {m.content || (busy && i === msgs.length - 1 ? "Thinking…" : "")}
              </div>
              {!!m.tools?.length && <div className="mt-1 text-xs text-muted-foreground">Used: {[...new Set(m.tools)].join(", ")}</div>}
            </div>
          ))}
          <div ref={end} />
        </div>
        <form onSubmit={send} className="flex gap-2 border-t p-3">
          <Input aria-label="Message" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about the Group HR Scorecard…" className="flex-1" />
          <Button type="submit" disabled={busy}>Send</Button>
        </form>
      </section>
    </div>
  );
}

export default function Copilot() {
  return <Suspense fallback={null}><Chat /></Suspense>;
}
