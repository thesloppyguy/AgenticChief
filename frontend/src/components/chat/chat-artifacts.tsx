"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, download } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ChatArtifact } from "./types";

const STATUS_COLOR: Record<string, string> = {
  green: "#0E6B57",
  amber: "#B07327",
  red: "#B23A34",
};

function BarRow({
  label,
  value,
  max,
  color = "#0E6B57",
  suffix = "",
}: {
  label: string;
  value: number;
  max: number;
  color?: string;
  suffix?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="grid grid-cols-[1fr_minmax(0,1fr)_3rem] items-center gap-2 text-xs">
      <span className="truncate text-muted-foreground">{label}</span>
      <div className="h-2 overflow-hidden rounded bg-muted">
        <div className="h-full rounded" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-right tabular-nums font-medium">
        {value}
        {suffix}
      </span>
    </div>
  );
}

function DualBar({
  label,
  demand,
  supply,
}: {
  label: string;
  demand: number;
  supply: number;
}) {
  const max = Math.max(demand, supply, 1);
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-foreground">{label}</div>
      <BarRow label="Demand" value={demand} max={max} color="#38454F" />
      <BarRow label="Supply" value={supply} max={max} color="#0E6B57" />
    </div>
  );
}

function StackRow({
  label,
  ready,
  pipeline,
  gap,
}: {
  label: string;
  ready: number;
  pipeline: number;
  gap: number;
}) {
  const total = ready + pipeline + gap || 1;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {ready}/{pipeline}/{gap}
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded bg-muted">
        <div style={{ width: `${(ready / total) * 100}%`, background: "#0E6B57" }} />
        <div style={{ width: `${(pipeline / total) * 100}%`, background: "#5A5FD8" }} />
        <div style={{ width: `${(gap / total) * 100}%`, background: "#B23A34" }} />
      </div>
    </div>
  );
}

function ArtifactBody({ artifact }: { artifact: ChatArtifact }) {
  if (artifact.kind === "skills_demand_supply" && artifact.domains?.length) {
    return (
      <div className="space-y-3">
        {artifact.domains.map((d) => (
          <DualBar
            key={String(d.label)}
            label={String(d.label)}
            demand={Number(d.demand) || 0}
            supply={Number(d.supply) || 0}
          />
        ))}
      </div>
    );
  }
  if (artifact.kind === "succession_stack" && artifact.functions?.length) {
    return (
      <div className="space-y-3">
        {artifact.functions.map((f) => (
          <StackRow
            key={String(f.function)}
            label={String(f.function)}
            ready={Number(f.ready_now) || 0}
            pipeline={Number(f.ready_1_2y) || 0}
            gap={Number(f.no_successor) || 0}
          />
        ))}
        <p className="text-[11px] text-muted-foreground">
          Ready now · Ready 1–2y · No successor
        </p>
      </div>
    );
  }
  if (artifact.kind === "scorecard_summary") {
    const pillars = artifact.pillars || [];
    const max = 100;
    return (
      <div className="space-y-3">
        {artifact.overall != null && (
          <div className="text-sm">
            Overall{" "}
            <span className="font-semibold tabular-nums">{artifact.overall}</span>
            {artifact.status ? (
              <span className="ml-2 text-xs text-muted-foreground">{artifact.status}</span>
            ) : null}
          </div>
        )}
        {pillars.map((p) => (
          <BarRow
            key={String(p.key || p.label)}
            label={String(p.label || p.key)}
            value={Number(p.score) || 0}
            max={max}
            color={STATUS_COLOR[p.status || ""] || "#38454F"}
          />
        ))}
      </div>
    );
  }
  if (
    (artifact.kind === "kpi_bars" || artifact.kind === "ic_compare") &&
    artifact.items?.length
  ) {
    const max = Math.max(
      ...artifact.items.map((i) => Number(i.value) || 0),
      artifact.kind === "ic_compare" ? 100 : 1,
    );
    return (
      <div className="space-y-2">
        {artifact.items.map((i) => (
          <BarRow
            key={String(i.label)}
            label={String(i.label)}
            value={Number(i.value) || 0}
            max={max || 1}
            color={STATUS_COLOR[i.status || ""] || "#0E6B57"}
            suffix={i.unit || ""}
          />
        ))}
      </div>
    );
  }
  if (artifact.kind === "table" && artifact.rows?.length) {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          {artifact.columns?.length ? (
            <thead>
              <tr className="text-muted-foreground">
                {artifact.columns.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {artifact.rows.map((row, i) => (
              <tr key={i} className="border-t border-border/60">
                {row.map((cell, j) => (
                  <td key={j} className="py-1.5 pr-3">
                    {String(cell ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <pre className="overflow-x-auto text-[11px] text-muted-foreground">
      {JSON.stringify(artifact, null, 2)}
    </pre>
  );
}

export function ChatArtifacts({ artifacts }: { artifacts?: ChatArtifact[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  if (!artifacts?.length) return null;

  async function onExport(a: ChatArtifact) {
    const key = a.export_key;
    if (!key) return;
    setBusy(`export:${key}`);
    try {
      if (key === "scorecard") {
        await download("/reports/export/scorecard.csv", "scorecard.csv");
      } else {
        const kind = key.startsWith("workforce_") ? key.slice("workforce_".length) : key;
        await download(`/workforce/export/${kind}`, `workforce_${kind}.csv`);
      }
      toast.success("Export downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  async function onSchedule(a: ChatArtifact) {
    const reportKey = a.schedule_key;
    if (!reportKey) return;
    setBusy(`schedule:${reportKey}`);
    try {
      const out = await api<{ verdict: string; reason?: string; approval?: { id: number } }>(
        "/approvals",
        {
          method: "POST",
          body: JSON.stringify({
            action: "schedule_report",
            args: {
              report_key: reportKey,
              name: a.title || `Scheduled ${reportKey}`,
              cadence: { type: "weekly", weekday: 0, time: "07:00" },
              period: "current",
            },
            context: { reason: `Schedule from chat artifact: ${a.title || reportKey}` },
          }),
        },
      );
      if (out.verdict === "deny") {
        toast.error(out.reason || "Schedule denied by policy");
      } else {
        toast.success(
          out.approval?.id
            ? `Schedule proposed (#${out.approval.id}) — approve on Actions`
            : "Schedule proposed",
        );
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not schedule");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-3 space-y-3">
      {artifacts.map((a, i) => (
        <div
          key={`${a.kind}-${i}`}
          className={cn(
            "rounded-xl border border-border/80 bg-background/80 p-3 shadow-sm",
          )}
        >
          {a.title ? (
            <div className="mb-2 text-xs font-semibold tracking-tight text-foreground">
              {a.title}
            </div>
          ) : null}
          <ArtifactBody artifact={a} />
          <div className="mt-3 flex flex-wrap gap-2">
            {a.export_key ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy !== null}
                onClick={() => onExport(a)}
              >
                Export
              </Button>
            ) : null}
            {a.schedule_key ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={busy !== null}
                onClick={() => onSchedule(a)}
              >
                Schedule as workflow
              </Button>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
