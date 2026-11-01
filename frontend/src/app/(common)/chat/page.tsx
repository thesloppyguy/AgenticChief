"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowUp, Bot, Plus, Terminal, Users } from "lucide-react";
import { usePeriod } from "@/components/AppShell";
import { PageHeader } from "@/components/ui";
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
import { SESSIONS_CHANGED } from "@/lib/types";

const EXAMPLES = [
  { title: "Group score", body: "What is the Group score this month, and what moved?" },
  { title: "Missing data", body: "Which companies are missing Learning & Development data?" },
  { title: "Off-track companies", body: "Which companies are off track, and what is driving it?" },
  { title: "Weakest pillar", body: "Summarise the weakest pillar and its lowest-scoring KPIs." },
];


interface Msg { role: "user" | "assistant"; content: string; tools: string[]; done: boolean }

/** Specialist consults read differently from ordinary tools. */
function ToolTrace({ tools, live }: { tools: string[]; live: boolean }) {
  if (tools.length === 0) return null;
  return (
    <Trace className="mb-2">
      {[...new Set(tools)].map((t) => {
        const delegated = t === "consult_specialist" || t === "delegate";
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
  const agents = useApi<{ name: string; role: string }[]>("/agents");

  const patch = (fn: (m: Msg) => Msg) =>
    setMsgs((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));

  async function send(prompt?: string) {
    const body = (prompt ?? text).trim();
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
        onDone: (id) => {
          setSid(id);
          patch((m) => ({ ...m, done: true }));
          window.dispatchEvent(new Event(SESSIONS_CHANGED));
        },
      },
    );
    setBusy(false);
  }

  const options = [{ value: "", label: "Executive (default)" },
    ...(agents.data ?? [])
      .filter((a) => a.name !== "executive")
      .map((a) => ({ value: a.name, label: a.role }))];
  const hasSupervisor = false;

  const composer = (
    <InputGroup className="rounded-2xl border-transparent bg-muted/70 shadow-sm ring-1 ring-black/5">
      <InputGroupTextarea rows={2} value={text} placeholder="Ask anything about the group…"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
        }} />
      <InputGroupAddon align="block-end">
        <span className="text-xs text-muted-foreground">Period {period}</span>
        <InputGroupButton variant="default" size="icon-sm" className="ml-auto rounded-full bg-neutral-900 text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900"
          disabled={busy || !text.trim()} onClick={() => void send()} aria-label="Send">
          <ArrowUp className="size-4" />
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
  );

  return (
    <div className="flex h-[calc(100svh-5.5rem)] min-h-0 flex-col gap-4">
      <PageHeader
        title="Chat"
        subtitle="Ask the Executive. Numbers come from tools — nothing is invented by the model."
        actions={
          <>
            <Select items={options} value={agent} onValueChange={(v) => setAgent(String(v))}>
              <SelectTrigger size="sm" className="w-56 rounded-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" className="rounded-full"
              onClick={() => { setSid(null); setMsgs([]); }}>
              <Plus className="size-4" />New session
            </Button>
          </>
        }
      />

      {hasSupervisor && (
        <p className="flex gap-2 text-xs text-muted-foreground">
          <Bot className="size-4 shrink-0" />
          Pick <strong>CHRO Supervisor</strong> for a question spanning several pillars: it asks the
          specialists and says which one each finding came from.
        </p>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-card shadow-sm ring-1 ring-black/5 dark:ring-white/10">
        {msgs.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto p-6">
            <div className="w-full max-w-3xl space-y-6">
              <div className="space-y-2 text-center">
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-neutral-900 text-white shadow-sm dark:bg-neutral-100 dark:text-neutral-900">
                  <Bot className="size-6" />
                </div>
                <p className="text-muted-foreground">Good to see you</p>
                <h2 className="text-2xl font-semibold tracking-tight">How can I help today?</h2>
                <p className="text-sm text-muted-foreground">
                  Ask about scores, companies, pillars, or anything in your knowledge base.
                </p>
              </div>
              {composer}
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Try an example</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button key={ex.title} type="button" disabled={busy} onClick={() => void send(ex.body)}
                      className="rounded-2xl bg-muted/50 p-4 text-left shadow-sm ring-1 ring-black/5 transition-colors hover:bg-white dark:ring-white/10">
                      <div className="font-medium">{ex.title}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{ex.body}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <MessageScrollerProvider>
              <MessageScroller className="min-h-0 flex-1">
                <MessageScrollerViewport className="p-4">
                  <MessageScrollerContent>
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
            <div className="border-t p-3">{composer}</div>
          </>
        )}
      </div>
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
