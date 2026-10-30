"use client";
import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, getClaims } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { RunSummary, SnapshotRow } from "@/lib/types";

const RUN_STYLE: Record<string, string> = {
  succeeded: "border-success/30 bg-success/10 text-success",
  failed: "border-destructive/30 bg-destructive/10 text-destructive",
  interrupted: "border-warning/30 bg-warning/10 text-warning",
  running: "border-warning/30 bg-warning/10 text-warning",
  queued: "text-muted-foreground",
};

export default function ReportsPage() {
  const [period] = usePeriod();
  const runs = useApi<RunSummary[]>("/workflows/runs");
  const snaps = useApi<SnapshotRow[]>("/reports/snapshots");
  const [busy, setBusy] = useState(false);
  const me = getClaims();

  async function generate() {
    setBusy(true);
    try {
      const run = await api<RunSummary>("/workflows/monthly-review/runs", {
        method: "POST", body: JSON.stringify({ period }),
      });
      toast.success(`Review started for ${period}.`);
      runs.reload();
      // The run streams its steps; the detail page polls for them.
      window.location.href = `/reports/${run.id}`;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start the review");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Reports</h1>
          <p className="text-sm text-muted-foreground">
            The monthly leadership review, and the immutable snapshots published from it.
          </p>
        </div>
        {me?.companies === null && (
          <Button onClick={generate} disabled={busy}>
            {busy ? "Starting…" : `Generate review for ${period}`}
          </Button>
        )}
      </div>

      <Tabs defaultValue="runs">
        <TabsList>
          <TabsTrigger value="runs">Review runs</TabsTrigger>
          <TabsTrigger value="published">Published</TabsTrigger>
        </TabsList>

        <TabsContent value="runs" className="mt-4">
          <Card title="Runs">
            <Loading error={runs.error} loading={runs.loading && !runs.data} />
            {runs.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">No runs yet.</p>
            )}
            <ul className="divide-y">
              {runs.data?.map((r) => (
                <li key={r.id}>
                  <Link href={`/reports/${r.id}`}
                    className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm hover:underline">
                    <span className="flex items-center gap-2">
                      <span className="font-medium">{label(r.workflow.replace("def:", ""))}</span>
                      <span className="tabular-nums text-muted-foreground">{r.period}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {r.requested_by} · {new Date(r.created_at).toLocaleDateString()}
                      </span>
                      <Badge variant="outline" className={cn(RUN_STYLE[r.status])}>
                        {label(r.status)}
                      </Badge>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </TabsContent>

        <TabsContent value="published" className="mt-4">
          <Card title="Published snapshots">
            <p className="mb-3 text-sm text-muted-foreground">
              A published snapshot is immutable and content-hashed: it cannot be edited or deleted, and
              it keeps the scoring rules it was produced under.
            </p>
            <Loading error={snaps.error} loading={snaps.loading && !snaps.data} />
            {snaps.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">Nothing published yet.</p>
            )}
            <ul className="divide-y">
              {snaps.data?.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{label(s.kind)}</span>
                    <span className="tabular-nums text-muted-foreground">{s.period}</span>
                    <Badge variant="outline">rules v{s.calc_version}</Badge>
                  </span>
                  <span className="flex items-center gap-3">
                    <code className="text-[10px] text-muted-foreground">
                      {s.content_hash?.slice(0, 12)}
                    </code>
                    <span className="text-xs text-muted-foreground">{s.created_by}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
