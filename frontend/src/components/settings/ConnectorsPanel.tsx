"use client";

import { useState } from "react";
import { Box, Database, Terminal } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { usePeriod } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui";
import {
  MetricCard,
  PanelEmpty,
  PanelIntro,
  PanelShell,
  StatusPill,
} from "@/components/settings/panel-chrome";
import type { SourcesStatusEnvelope } from "@/lib/types";

type Status = {
  mcp_enabled: boolean;
  mcp_servers_path: string;
  anthropic_configured: boolean;
  vector_store_path: string;
  company_dir: string;
  servers: { name: string; transport: string }[];
  gateway: { ready: boolean; tool_count: number; connected_servers: string[] };
  error?: string;
};

export function ConnectorsPanel({ mcpOnly = false }: { mcpOnly?: boolean }) {
  const { data, error, loading } = useApi<Status>("/setup/status");

  return (
    <PanelShell className="min-h-0 overflow-y-auto">
      <PanelIntro
        title={mcpOnly ? "MCP Tools" : "Connectors"}
        description={
          mcpOnly
            ? "MCP servers from mcp_servers.json and the live gateway process."
            : "HR source health plus MCP connectors from env and mcp_servers.json."
        }
        count={
          data
            ? `${data.servers.length} servers · ${data.gateway.tool_count} tools`
            : undefined
        }
      />
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="space-y-4">
          {!mcpOnly && <HrSourcesSection />}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {!mcpOnly && (
              <MetricCard
                label="Anthropic API"
                ok={data.anthropic_configured}
                value={data.anthropic_configured ? "Configured" : "Missing"}
              />
            )}
            <MetricCard
              label="MCP gateway"
              ok={data.mcp_enabled}
              value={data.mcp_enabled ? "Enabled" : "Disabled"}
            />
            <MetricCard
              label="Gateway ready"
              ok={data.gateway.ready}
              value={data.gateway.ready ? "Online" : "Offline"}
            />
          </div>

          {!mcpOnly && (
            <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
              <div className="mb-3 text-[11px] font-semibold uppercase text-muted-foreground">
                Paths
              </div>
              <div className="space-y-2.5">
                <PathRow label="Config" value={data.mcp_servers_path} />
                <PathRow label="Chroma" value={data.vector_store_path} />
                <PathRow label="Company" value={data.company_dir} />
              </div>
            </div>
          )}

          <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
            <div className="flex items-center justify-between gap-2 border-b border-black/5 px-4 py-3 dark:border-white/10">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                {mcpOnly ? (
                  <Terminal className="size-4 text-muted-foreground" />
                ) : (
                  <Box className="size-4 text-muted-foreground" />
                )}
                Servers
              </div>
              <Badge variant="outline">{data.gateway.tool_count} tools</Badge>
            </div>
            {data.servers.length === 0 ? (
              <div className="p-3">
                <PanelEmpty
                  icon={mcpOnly ? Terminal : Box}
                  title="No servers listed"
                  description="Add entries to mcp_servers.json to expose MCP tools through the gateway."
                />
              </div>
            ) : (
              <ul className="divide-y divide-black/5 dark:divide-white/10">
                {data.servers.map((s) => {
                  const connected = data.gateway.connected_servers.includes(s.name);
                  return (
                    <li
                      key={s.name}
                      className="flex flex-wrap items-center justify-between gap-2 px-4 py-3.5"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-foreground/70">
                          <Terminal className="size-3.5" />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-foreground">
                            {s.name}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {s.transport}
                          </div>
                        </div>
                      </div>
                      <StatusPill
                        ok={connected}
                        label={connected ? "Connected" : "Idle"}
                      />
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {data.error && (
            <p className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {data.error}
            </p>
          )}
        </div>
      )}
    </PanelShell>
  );
}

function HrSourcesSection() {
  const [period] = usePeriod();
  const { data, error, loading, reload } = useApi<SourcesStatusEnvelope>("/sources/status");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function generateProfiles() {
    setBusy("generate");
    setMsg(null);
    try {
      await api("/mock-sources/admin/generate", { method: "POST" });
      setMsg("AI profile generation started. Refresh status in a moment.");
      reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Generate failed");
    } finally {
      setBusy(null);
    }
  }

  async function sync(source?: string) {
    setBusy(source ?? "all");
    setMsg(null);
    try {
      const path = source ? `/sources/${source}/sync` : "/sources/sync";
      await api(path, { method: "POST", body: JSON.stringify({ period }) });
      setMsg(source ? `Synced ${source} for ${period}.` : `Synced all sources for ${period}.`);
      reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/5 px-4 py-3 dark:border-white/10">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Database className="size-4 text-muted-foreground" />
          HR Sources
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="rounded-full"
            disabled={!!busy}
            onClick={() => void generateProfiles()}
          >
            {busy === "generate" ? "Generating…" : "Generate AI profiles"}
          </Button>
          <Button
            size="sm"
            className="rounded-full"
            disabled={!!busy}
            onClick={() => void sync()}
          >
            {busy === "all" ? "Syncing…" : `Sync ${period}`}
          </Button>
        </div>
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="space-y-3 p-4">
          <p className="rounded-xl bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
            {data.mock_sources_enabled
              ? "AI-backed live adapters are on — live extractors call /mock-sources/*."
              : "Using stub fixture mode — enable mock sources via scripts.setup_mock_sources --write-env."}
            {" "}
            SLA {data.sla_hours}h · AI key {data.ai_configured ? "configured" : "missing"}.
          </p>
          <ul className="divide-y divide-black/5 rounded-xl ring-1 ring-black/5 dark:divide-white/10 dark:ring-white/10">
            {data.sources.map((s) => (
              <li
                key={s.source}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-3"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{s.label}</div>
                  <div className="text-xs text-muted-foreground">
                    {s.mode}
                    {s.data_origin ? ` · origin ${s.data_origin}` : ""}
                    {s.age_hours != null ? ` · ${s.age_hours.toFixed(1)}h ago` : ""}
                    {s.last_run
                      ? ` · last ${s.last_run.status} (${s.last_run.period})`
                      : " · no runs yet"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill
                    ok={s.freshness === "fresh"}
                    label={s.freshness ?? "unknown"}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    className="rounded-full text-xs"
                    disabled={!!busy}
                    onClick={() => void sync(s.source)}
                  >
                    {busy === s.source ? "…" : "Sync"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
        </div>
      )}
    </div>
  );
}

function PathRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[72px_1fr] sm:items-center sm:gap-3">
      <span className="text-xs font-semibold text-muted-foreground">{label}</span>
      <code className="break-all rounded-xl bg-muted/60 px-3 py-2 font-mono text-[11px] leading-relaxed text-foreground/85">
        {value}
      </code>
    </div>
  );
}
