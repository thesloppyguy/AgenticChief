"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { api } from "@/lib/api";
import { streamChat } from "@/lib/chat";
import { useApi } from "@/lib/hooks";

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

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      <aside className="w-56 shrink-0 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <button onClick={() => { setSid(null); setMsgs([]); }} className="mb-2 w-full rounded bg-slate-900 px-2 py-1.5 text-white">New session</button>
        <ul>
          {sessions.data?.map((s) => (
            <li key={s.id}><button onClick={() => open(s.id)} className={`w-full truncate rounded px-2 py-1 text-left hover:bg-slate-100 ${s.id === sid ? "bg-slate-100" : ""}`}>{s.title}</button></li>
          ))}
        </ul>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-2 text-sm">
          <label htmlFor="agent" className="text-slate-500">Agent</label>
          <select id="agent" value={agent} onChange={(e) => setAgent(e.target.value)} className="rounded border border-slate-300 px-2 py-1">
            <option value="">Copilot (default)</option>
            {agents.data?.map((a) => <option key={a.key} value={a.key}>{a.name}</option>)}
          </select>
          {agent && <span className="text-xs text-slate-500">{agents.data?.find((a) => a.key === agent)?.description}</span>}
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {msgs.length === 0 && (
            <p className="text-sm text-slate-500">Try: “What is the current Group HR score?”, “Which pillars need attention?”, “How is top talent retention calculated?”</p>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <div className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-left text-sm ${m.role === "user" ? "bg-slate-900 text-white" : "bg-slate-100"}`}>
                {m.content || (busy && i === msgs.length - 1 ? "Thinking…" : "")}
              </div>
              {!!m.tools?.length && <div className="mt-1 text-xs text-slate-500">Used: {[...new Set(m.tools)].join(", ")}</div>}
            </div>
          ))}
          <div ref={end} />
        </div>
        <form onSubmit={send} className="flex gap-2 border-t border-slate-200 p-3">
          <input aria-label="Message" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about the Group HR Scorecard…" className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm" />
          <button disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50">Send</button>
        </form>
      </section>
    </div>
  );
}

export default function Copilot() {
  return <Suspense fallback={null}><Chat /></Suspense>;
}
