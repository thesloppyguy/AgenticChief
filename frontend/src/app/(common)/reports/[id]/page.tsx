"use client";
import { use, useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";
import ReportView from "@/components/ReportView";
import WorkflowResultView, {
  isMonthlyReport,
  isWorkflowResult,
} from "@/components/WorkflowResultView";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, download, getClaims } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { RunDetail } from "@/lib/types";

const STEP_ICON = { done: CheckCircle2, failed: XCircle, started: Loader2, skipped: CircleDashed };
const STEP_STYLE: Record<string, string> = {
  done: "text-success", failed: "text-destructive",
  started: "text-muted-foreground animate-spin", skipped: "text-muted-foreground",
};

export default function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading, reload } = useApi<RunDetail>(`/workflows/runs/${id}`);
  const [busy, setBusy] = useState(false);
  const me = getClaims();
  const running = data?.status === "running" || data?.status === "queued";
  const monthly = data?.result != null && isMonthlyReport(data.result);
  const workflowKey = data?.workflow?.replace(/^def:/, "") || "";

  // A run streams its steps, so poll while it is in flight and stop as soon as it settles.
  useEffect(() => {
    if (!running) return;
    const t = setInterval(reload, 2000);
    return () => clearInterval(t);
  }, [running, reload]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold">
                {label(workflowKey)} — {data.period}
              </h1>
              <p className="text-sm text-muted-foreground">
                Run #{data.id} · asked by {data.requested_by}
                {data.error && <span className="text-destructive"> · {data.error}</span>}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {data.status === "succeeded" && monthly && (
                <>
                  <Button variant="outline" size="sm"
                    onClick={() => download(`/workflows/runs/${id}/pdf`, `review-${data.period}.pdf`)}>
                    Download PDF
                  </Button>
                  {me?.role === "admin" && (
                    <Button size="sm" disabled={busy}
                      onClick={() => act(
                        () => api("/approvals", {
                          method: "POST",
                          body: JSON.stringify({ action: "publish_monthly_report", args: { run_id: Number(id) } }),
                        }),
                        "Publishing proposed — a second admin must approve it.")}>
                      Propose publishing
                    </Button>
                  )}
                </>
              )}
              {(data.status === "interrupted" || data.status === "failed") && (
                <Button size="sm" disabled={busy}
                  onClick={() => act(() => api(`/workflows/runs/${id}/resume`, { method: "POST" }),
                    "Resuming after the last completed step.")}>
                  Resume
                </Button>
              )}
            </div>
          </div>

          <Card title="Steps">
            <ol className="space-y-2">
              {data.steps.map((s) => {
                const last = [...data.events].reverse().find((e) => e.step === s.key);
                const state = s.done ? "done" : last?.status ?? "pending";
                const Icon = STEP_ICON[state as keyof typeof STEP_ICON] ?? CircleDashed;
                return (
                  <li key={s.key} className="flex items-center gap-2 text-sm">
                    <Icon className={cn("size-4 shrink-0", STEP_STYLE[state] ?? "text-muted-foreground")} />
                    <span className={cn(!s.done && "text-muted-foreground")}>{s.label}</span>
                  </li>
                );
              })}
            </ol>
            {data.events.length > 0 && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-muted-foreground">
                  Event log ({data.events.length})
                </summary>
                <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                  {data.events.map((e) => (
                    <li key={e.seq} className="flex gap-2">
                      <span className="tabular-nums">{new Date(e.at).toLocaleTimeString()}</span>
                      <Badge variant="outline" className="text-[10px]">{e.status}</Badge>
                      <span>{e.message}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </Card>

          {monthly && data.result ? <ReportView r={data.result} /> : null}

          {!monthly && data.result && isWorkflowResult(data.result) ? (
            <WorkflowResultView result={data.result} />
          ) : null}

          {!monthly && data.result && !isWorkflowResult(data.result) ? (
            <Card title="Result">
              <pre className="overflow-x-auto text-xs">{JSON.stringify(data.result, null, 2)}</pre>
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}
