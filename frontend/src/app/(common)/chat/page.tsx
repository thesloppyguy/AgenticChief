"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUp, Bot, Plus, Terminal, Users } from "lucide-react";
import { usePeriod } from "@/components/AppShell";
import { Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import {
  InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea,
} from "@/components/ui/input-group";
import {
  Message, MessageContent, MessageGroup, MessageHeader,
} from "@/components/ui/message";
import {
  MessageScroller, MessageScrollerButton, MessageScrollerContent,
  MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace";
import { streamChat } from "@/lib/chat";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AssetRow, SessionRow } from "@/lib/types";

interface Msg { role: "user" | "assistant"; content: string; tools: string[]; done: boolean }

/** A delegate call is a sub-agent doing the work, so it reads differently from an ordinary tool. */
function ToolTrace({ tools, live }: { tools: string[]; live: boolean }) {
  if (tools.length === 0) return null;
  return (
    <Trace className="mb-2">
      {[...new Set(tools)].map((t) => {
        const delegated = t === "delegate";
        return (
          <TraceLine key={t} status={live ? "running" : undefined}>
            <TraceIcon>
              {delegated ? <Users className="size-3.5" /> : <Terminal className="size-3.5" />}
            </TraceIcon>
            <TraceTitle>
              {delegated ? "Asked a specialist" : `Used ${label(t.replace(/^cap_/, ""))}`}
            </TraceTitle>
          </TraceLine>
        );
      })}
    </Trace>
  );
}

function Chat() {
  const params = useSearchParams();
  const [period] = usePeriod();
  const [agent, setAgent] = useState(params.get("agent") ?? "");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [sid, setSid] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const agents = useApi<AssetRow[]>("/agents");
  const sessions = useApi<SessionRow[]>("/copilot/sessions");

  const patch = (fn: (m: Msg) => Msg) =>
    setMsgs((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));

  async function send() {
    const body = text.trim();
    if (!body || busy) return;
    setText("");
    setBusy(true);
    setMsgs((all) => [...all,
      { role: "user", content: body, tools: [], done: true },
      { role: "assistant", content: "", tools: [], done: false }]);
    await streamChat(
      { message: body, session_id: sid, period, ...(agent ? { agent_key: agent } : {}) },
      {
        onChunk: (c) => patch((m) => ({ ...m, content: m.content + c })),
        onTool: (n) => patch((m) => ({ ...m, tools: [...m.tools, n] })),
        onError: (e) => patch((m) => ({ ...m, content: e, done: true })),
        onDone: (id) => { setSid(id); patch((m) => ({ ...m, done: true })); sessions.reload(); },
      },
    );
    setBusy(false);
  }

  const options = [{ value: "", label: "Copilot (default)" },
    ...(agents.data ?? []).map((a) => ({ value: a.key, label: a.name }))];

  return (
    <div className="grid h-[calc(100vh-6rem)] gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
      <div className="flex min-h-0 flex-col">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold">Ask</h1>
            <p className="text-sm text-muted-foreground">
              Every number comes from a tool result. Nothing here is calculated by the model.
            </p>
          </div>
          <Select items={options} value={agent} onValueChange={(v) => setAgent(String(v))}>
            <SelectTrigger size="sm" className="w-56"><SelectValue /></SelectTrigger>
            <SelectContent>
              {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <MessageScrollerProvider>
          <MessageScroller className="min-h-0 flex-1 rounded-lg border">
            <MessageScrollerViewport className="p-4">
              <MessageScrollerContent>
                {msgs.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    Try “What is the Group score this month, and what moved?” or
                    “Which companies are missing Learning &amp; Development data?”
                  </p>
                )}
                <MessageGroup>
                  {msgs.map((m, i) => (
                    <MessageScrollerItem key={i} scrollAnchor={i === msgs.length - 1}>
                      <Message align={m.role === "user" ? "end" : "start"}>
                        <MessageContent>
                          {m.role === "assistant" && (
                            <>
                              <MessageHeader>
                                {agent ? options.find((o) => o.value === agent)?.label : "Copilot"}
                              </MessageHeader>
                              <ToolTrace tools={m.tools} live={!m.done} />
                            </>
                          )}
                          <Bubble variant={m.role === "user" ? "default" : "muted"}
                            align={m.role === "user" ? "end" : "start"}>
                            <BubbleContent className="whitespace-pre-wrap">
                              {m.content || (m.done ? "" : "Thinking…")}
                            </BubbleContent>
                          </Bubble>
                        </MessageContent>
                      </Message>
                    </MessageScrollerItem>
                  ))}
                </MessageGroup>
              </MessageScrollerContent>
            </MessageScrollerViewport>
            <MessageScrollerButton direction="end" />
          </MessageScroller>
        </MessageScrollerProvider>

        <div className="mt-3">
          <InputGroup>
            <InputGroupTextarea rows={2} value={text} placeholder="Ask about the scorecard…"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
              }} />
            <InputGroupAddon align="block-end">
              <span className="text-xs text-muted-foreground">Period {period}</span>
              <InputGroupButton size="icon-sm" className="ml-auto" disabled={busy || !text.trim()}
                onClick={() => void send()} aria-label="Send">
                <ArrowUp className="size-4" />
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
        </div>
      </div>

      <aside className="hidden min-h-0 flex-col lg:flex">
        <Button variant="outline" size="sm" className="mb-2"
          onClick={() => { setSid(null); setMsgs([]); }}>
          <Plus className="size-4" />New session
        </Button>
        <Loading error={sessions.error} loading={sessions.loading && !sessions.data} />
        <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {sessions.data?.map((s) => (
            <li key={s.id}>
              <Link href={`/chat/${s.id}`}
                className="block rounded px-2 py-1.5 text-sm transition-colors hover:bg-muted/50">
                <span className="line-clamp-1">{s.title}</span>
                <span className="text-xs text-muted-foreground">
                  {s.message_count} messages · {new Date(s.last_at).toLocaleDateString()}
                </span>
              </Link>
            </li>
          ))}
          {sessions.data?.length === 0 && (
            <li className="px-2 text-sm text-muted-foreground">No sessions yet.</li>
          )}
        </ul>
        {agents.data?.some((a) => a.key === "chro_supervisor") && (
          <p className="mt-3 flex gap-2 rounded-lg border p-2 text-xs text-muted-foreground">
            <Bot className="size-4 shrink-0" />
            Pick <strong>CHRO Supervisor</strong> for a question spanning several pillars: it asks the
            specialists and says which one each finding came from.
          </p>
        )}
      </aside>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <Chat />
    </Suspense>
  );
}
