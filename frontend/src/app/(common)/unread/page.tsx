"use client";

import Link from "next/link";
import { toast } from "sonner";
import { Bell, CheckCheck } from "lucide-react";
import { Card, Loading, PageHeader } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { AlertItem, UnreadSummary } from "@/lib/types";

const SEV: Record<string, string> = {
  urgent: "border-destructive/40 bg-destructive/10 text-destructive",
  high: "border-destructive/30 bg-destructive/10 text-destructive",
  medium: "border-warning/30 bg-warning/10 text-warning",
  low: "border-border bg-muted/40 text-muted-foreground",
};

export default function UnreadPage() {
  const alerts = useApi<AlertItem[]>("/alerts?unread_only=true&limit=100");
  const summary = useApi<UnreadSummary>("/unread/summary");

  async function markOne(id: number) {
    try {
      await api(`/alerts/${id}/read`, { method: "POST" });
      toast.success("Marked read");
      alerts.reload();
      summary.reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not mark read");
    }
  }

  async function markAll() {
    try {
      const res = await api<{ marked: number }>("/alerts/read-all", { method: "POST" });
      toast.success(res.marked ? `Marked ${res.marked} read` : "Nothing unread");
      alerts.reload();
      summary.reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not mark all read");
    }
  }

  const items = alerts.data ?? [];
  const pending = summary.data?.approvals_pending ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Unread"
        subtitle="Alerts waiting for you, plus a shortcut to pending approvals."
        actions={
          <div className="flex flex-wrap gap-2">
            {pending > 0 ? (
              <Button
                variant="outline"
                size="sm"
                render={<Link href="/actions" />}
                nativeButton={false}
              >
                {pending} pending {pending === 1 ? "approval" : "approvals"}
              </Button>
            ) : null}
            <Button size="sm" disabled={!items.length} onClick={markAll}>
              <CheckCheck className="size-4" />
              Mark all read
            </Button>
          </div>
        }
      />

      <Loading error={alerts.error} loading={alerts.loading && !alerts.data} />

      {!alerts.loading && items.length === 0 ? (
        <Card title="All caught up">
          <p className="text-sm text-muted-foreground">
            No unread alerts. Pending approvals still live under{" "}
            <Link href="/actions" className="underline underline-offset-2">
              Actions
            </Link>
            .
          </p>
        </Card>
      ) : null}

      <ul className="space-y-2">
        {items.map((a) => (
          <li
            key={a.id}
            className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-border/70 bg-card px-4 py-3"
          >
            <div className="flex min-w-0 gap-3">
              <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border bg-background">
                <Bell className="size-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{a.title}</span>
                  <Badge
                    variant="outline"
                    className={cn("text-[10px]", SEV[a.severity] || SEV.low)}
                  >
                    {a.severity}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    {label(a.kind)}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  {[a.entity, a.period, new Date(a.created_at).toLocaleString()]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => markOne(a.id)}>
              Mark read
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
