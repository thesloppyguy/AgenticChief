"use client";

import { useMemo, useState } from "react";
import { Box, Terminal, Wrench } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui";
import {
  PanelEmpty,
  PanelIntro,
  PanelShell,
  StatusPill,
} from "@/components/settings/panel-chrome";

type CatalogTool = {
  name: string;
  description: string;
  source: "builtin" | "mcp" | "custom";
  group: string;
  enabled: boolean;
  server?: string;
  active_version?: number;
  workflow_approved_version?: number | null;
  kind?: string;
};

type Catalog = {
  builtin: CatalogTool[];
  mcp: CatalogTool[];
  custom: CatalogTool[];
  counts: { builtin: number; mcp: number; custom: number; total: number };
};

type Tab = "all" | "builtin" | "mcp" | "custom";

export function ToolsPanel() {
  const { data, error, loading, reload } = useApi<Catalog>("/tools/catalog");
  const [tab, setTab] = useState<Tab>("all");

  async function toggle(name: string, enabled: boolean) {
    await api(`/saved-tools/${name}/enable`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
    reload();
  }

  const rows = useMemo(() => {
    if (!data) return [];
    if (tab === "builtin") return data.builtin;
    if (tab === "mcp") return data.mcp;
    if (tab === "custom") return data.custom;
    return [...data.builtin, ...data.mcp, ...data.custom];
  }, [data, tab]);

  const byGroup = useMemo(() => {
    const map: Record<string, CatalogTool[]> = {};
    for (const t of rows) {
      (map[t.group] ||= []).push(t);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [rows]);

  return (
    <PanelShell className="min-h-0 overflow-y-auto">
      <PanelIntro
        title="Tools"
        description="Builtin Executive tools, MCP connectors, and any custom tools saved from chat."
        count={data ? `${data.counts.total} tools` : undefined}
      />
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="mb-4 flex flex-wrap gap-1.5">
            {(
              [
                ["all", `All (${data.counts.total})`],
                ["builtin", `Builtin (${data.counts.builtin})`],
                ["mcp", `MCP (${data.counts.mcp})`],
                ["custom", `Custom (${data.counts.custom})`],
              ] as const
            ).map(([key, label]) => (
              <Button
                key={key}
                type="button"
                size="sm"
                variant="ghost"
                className={
                  tab === key
                    ? "rounded-full bg-muted font-medium text-foreground ring-1 ring-black/5"
                    : "rounded-full text-muted-foreground"
                }
                onClick={() => setTab(key)}
              >
                {label}
              </Button>
            ))}
          </div>

          {rows.length === 0 ? (
            <PanelEmpty
              icon={Wrench}
              title={
                tab === "custom"
                  ? "No custom tools yet"
                  : tab === "mcp"
                    ? "No MCP tools connected"
                    : "No tools found"
              }
              description={
                tab === "custom"
                  ? "When the Executive saves a reusable tool during a chat, it will show up here."
                  : tab === "mcp"
                    ? "Enable the MCP gateway and connect servers in mcp_servers.json to expose tools."
                    : "No tools are registered yet."
              }
            />
          ) : (
            <div className="space-y-5">
              {byGroup.map(([group, tools]) => (
                <section key={group} className="space-y-2">
                  <div className="px-0.5 text-[11px] font-semibold uppercase text-muted-foreground">
                    {group}
                  </div>
                  <ul className="space-y-2">
                    {tools.map((t) => (
                      <ToolRow key={`${t.source}:${t.name}`} tool={t} onToggle={toggle} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </PanelShell>
  );
}

function ToolRow({
  tool,
  onToggle,
}: {
  tool: CatalogTool;
  onToggle: (name: string, enabled: boolean) => void;
}) {
  const Icon =
    tool.source === "mcp" ? Terminal : tool.source === "custom" ? Wrench : Box;

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
      <div className="flex min-w-0 items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-muted text-foreground/70">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <div className="truncate text-sm font-semibold text-foreground">
              {tool.name}
            </div>
            <Badge variant="outline">{tool.source}</Badge>
            {tool.source === "custom" && (
              <StatusPill
                ok={tool.enabled}
                label={tool.enabled ? "Enabled" : "Disabled"}
              />
            )}
          </div>
          <div className="text-pretty text-sm leading-relaxed text-muted-foreground">
            {tool.description || "No description"}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {tool.active_version != null && (
              <Badge variant="outline">v{tool.active_version}</Badge>
            )}
            {tool.workflow_approved_version != null && (
              <Badge variant="outline">
                workflow v{tool.workflow_approved_version}
              </Badge>
            )}
            {tool.server && <Badge variant="outline">{tool.server}</Badge>}
          </div>
        </div>
      </div>
      {tool.source === "custom" && (
        <Button
          size="sm"
          variant="outline"
          className="rounded-full"
          onClick={() => onToggle(tool.name, !tool.enabled)}
        >
          {tool.enabled ? "Disable" : "Enable"}
        </Button>
      )}
    </li>
  );
}
