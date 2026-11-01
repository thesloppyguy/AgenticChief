"use client";

import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Loading } from "@/components/ui";
import {
  DetailPane,
  PanelEmpty,
  PanelIntro,
  PanelShell,
  SideList,
  SideListItem,
  SideListSection,
} from "@/components/settings/panel-chrome";

type AgentMeta = {
  name: string;
  role: string;
  model: string;
  deep_reasoning: boolean;
  visibility: string;
  has_override: boolean;
};

type AgentDetail = AgentMeta & {
  prompt: string;
  prompt_default?: string;
  instructions: string | null;
};

export function AgentsPanel() {
  const { data, error, loading, reload } = useApi<AgentMeta[]>("/agents");
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useApi<AgentDetail>(selected ? `/agents/${selected}` : null);
  const [instructions, setInstructions] = useState("");
  const [instructionsDirty, setInstructionsDirty] = useState(false);
  const [testQuery, setTestQuery] = useState("");
  const [testOut, setTestOut] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const core = (data || []).filter((a) => a.visibility === "core");
  const internal = (data || []).filter((a) => a.visibility !== "core");
  const d =
    detail.data && selected && detail.data.name === selected ? detail.data : null;
  const systemPrompt = (d?.prompt || d?.prompt_default || "").trim();

  useEffect(() => {
    if (!d || instructionsDirty) return;
    setInstructions(d.instructions || "");
  }, [d, instructionsDirty]);

  function pick(name: string) {
    setSelected(name);
    setTestOut(null);
    setInstructions("");
    setInstructionsDirty(false);
  }

  async function saveInstructions() {
    if (!selected) return;
    setBusy(true);
    try {
      await api(`/agents/${selected}`, {
        method: "PATCH",
        body: JSON.stringify({ instructions: instructions || null }),
      });
      setInstructionsDirty(false);
      detail.reload();
      reload();
    } finally {
      setBusy(false);
    }
  }

  async function resetAgent() {
    if (!selected) return;
    setBusy(true);
    try {
      await api(`/agents/${selected}`, { method: "DELETE" });
      setInstructions("");
      setInstructionsDirty(false);
      detail.reload();
      reload();
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    if (!selected || !testQuery.trim()) return;
    setBusy(true);
    setTestOut(null);
    try {
      const res = await api<{ response: string }>(`/agents/${selected}/test`, {
        method: "POST",
        body: JSON.stringify({
          query: testQuery,
          instructions: instructions || null,
        }),
      });
      setTestOut(res.response);
    } catch (e) {
      setTestOut(e instanceof Error ? e.message : "Test failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelShell>
      <PanelIntro
        title="Agents"
        description="Code-registered specialists with runtime overrides for prompts and instructions."
        count={data ? `${data.length} agents` : undefined}
      />
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="grid min-h-0 flex-1 gap-4 sm:grid-cols-[260px_1fr]">
          <SideList>
            <AgentList title="Core" agents={core} selected={selected} onPick={pick} />
            <AgentList
              title="Internal"
              agents={internal}
              selected={selected}
              onPick={pick}
            />
          </SideList>
          <DetailPane>
            {!selected && (
              <PanelEmpty
                icon={Bot}
                title="Select an agent"
                description="Choose a specialist from the list to view its model, edit instructions, or run a quick test."
              />
            )}
            {d && (
              <>
                <div className="flex items-start gap-3 border-b border-black/5 pb-4 dark:border-white/10">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-muted text-foreground">
                    <Bot className="size-5" />
                  </span>
                  <div className="min-w-0 space-y-2">
                    <div className="text-lg font-semibold text-foreground">{d.role}</div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="outline">{d.name}</Badge>
                      <Badge variant="outline">{d.model}</Badge>
                      {d.deep_reasoning && (
                        <Badge variant="outline">deep reasoning</Badge>
                      )}
                      {d.has_override && (
                        <Badge variant="outline">customized</Badge>
                      )}
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <Label>System prompt</Label>
                    <span className="text-[11px] text-muted-foreground">
                      Read-only · {systemPrompt.length.toLocaleString()} chars
                    </span>
                  </div>
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-black/5 bg-[#F7F7F6] p-3.5 font-mono text-[11px] leading-relaxed text-foreground dark:border-white/10 dark:bg-muted/40">
                    {systemPrompt || "No system prompt."}
                  </pre>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="agent-instructions">Additional instructions</Label>
                  <Textarea
                    id="agent-instructions"
                    className="min-h-24 rounded-xl"
                    value={instructions}
                    onChange={(e) => {
                      setInstructionsDirty(true);
                      setInstructions(e.target.value);
                    }}
                    maxLength={4000}
                    placeholder="Optional guidance layered on the built-in prompt…"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={saveInstructions}
                    className="rounded-full bg-neutral-900 px-4 text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={resetAgent}
                    className="rounded-full"
                  >
                    Reset
                  </Button>
                </div>
                <div className="space-y-2 rounded-2xl bg-muted/50 p-4">
                  <Label htmlFor="agent-test">Test query</Label>
                  <Textarea
                    id="agent-test"
                    className="min-h-16 rounded-xl bg-white dark:bg-background"
                    value={testQuery}
                    onChange={(e) => setTestQuery(e.target.value)}
                    placeholder="Ask this agent something…"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || !testQuery.trim()}
                    onClick={runTest}
                    className="rounded-full"
                  >
                    Run test
                  </Button>
                  {testOut && (
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-xl bg-white p-3 text-xs leading-relaxed text-foreground ring-1 ring-black/5 dark:bg-background dark:ring-white/10">
                      {testOut}
                    </pre>
                  )}
                </div>
              </>
            )}
          </DetailPane>
        </div>
      )}
    </PanelShell>
  );
}

function AgentList({
  title,
  agents,
  selected,
  onPick,
}: {
  title: string;
  agents: AgentMeta[];
  selected: string | null;
  onPick: (name: string) => void;
}) {
  if (!agents.length) return null;
  return (
    <SideListSection title={title}>
      {agents.map((a) => (
        <SideListItem
          key={a.name}
          icon={Bot}
          active={selected === a.name}
          onClick={() => onPick(a.name)}
          hint={
            a.has_override ? (
              <span
                className="size-1.5 shrink-0 rounded-full bg-neutral-700"
                title="Customized"
              />
            ) : undefined
          }
        >
          {a.role}
        </SideListItem>
      ))}
    </SideListSection>
  );
}
