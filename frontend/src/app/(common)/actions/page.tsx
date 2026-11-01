"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Card, Loading, PageHeader } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, getClaims } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { label } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Approval } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  pending: "border-warning/30 bg-warning/10 text-warning",
  approved: "border-success/30 bg-success/10 text-success",
  executed: "border-success/30 bg-success/10 text-success",
  rejected: "border-destructive/30 bg-destructive/10 text-destructive",
  denied: "border-destructive/30 bg-destructive/10 text-destructive",
  failed: "border-destructive/30 bg-destructive/10 text-destructive",
  changes_requested: "border-warning/30 bg-warning/10 text-warning",
};

const RISK_NOTE: Record<string, string> = {
  read: "Reads data only.",
  internal_write: "Changes our own records.",
  external_message: "Reaches someone outside the platform.",
  destructive: "Denied by policy.",
};

/** Context the backend's precheck attached: what changes, what depends on it, whether it is a rollback. */
function ContextBlock({ context }: { context: Record<string, unknown> | null }) {
  if (!context || Object.keys(context).length === 0) return null;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {Object.entries(context).map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{label(k)}</dt>
          <dd className="break-words">
            {typeof v === "string" ? v : <code className="text-xs">{JSON.stringify(v)}</code>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Detail({ id, onDecided }: { id: number; onDecided: () => void }) {
  const { data, error, loading, reload } = useApi<Approval>(`/approvals/${id}`);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const me = getClaims();

  if (!data) return <Loading error={error} loading={loading} />;

  // Four-eyes: the backend refuses this, and the UI says why rather than failing on click.
  const ownRequest = data.requested_by === me?.sub;
  const canDecide = me?.role === "admin" && data.status === "pending" && !ownRequest;

  async function decide(decision: string) {
    if (decision !== "approve" && !comment.trim()) {
      toast.error("A comment is required when rejecting or requesting changes.");
      return;
    }
    setBusy(decision);
    try {
      const out = await api<Approval>(`/approvals/${id}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, comment: comment.trim() || null }),
      });
      toast.success(`Request ${out.status}.`);
      setComment("");
      reload();
      onDecided();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className={cn(STATUS_STYLE[data.status])}>{label(data.status)}</Badge>
          <Badge variant="outline">{label(data.risk)}</Badge>
          <span className="text-xs text-muted-foreground">
            #{data.id} · asked by {data.requested_by} via {data.via}
          </span>
        </div>
        <h3 className="mt-2 font-medium">{data.summary}</h3>
        <p className="text-sm text-muted-foreground">{RISK_NOTE[data.risk]}</p>
      </div>

      <Card title="What this would do">
        <ContextBlock context={data.context} />
        <pre className="mt-3 overflow-x-auto rounded bg-muted p-3 text-xs">
          {JSON.stringify(data.args, null, 2)}
        </pre>
      </Card>

      {data.events?.length ? (
        <Card title="History">
          <ul className="space-y-1 text-sm">
            {data.events.map((e, i) => (
              <li key={i} className="flex flex-wrap gap-2">
                <span className="text-muted-foreground tabular-nums">
                  {new Date(e.at).toLocaleString()}
                </span>
                <span>{label(e.event)} — {e.actor}</span>
                {e.comment && <span className="text-muted-foreground">“{e.comment}”</span>}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {data.status === "pending" && (
        <Card title="Decide">
          {ownRequest ? (
            <p className="text-sm text-muted-foreground">
              You asked for this, so you cannot approve it. A second admin must decide.
            </p>
          ) : me?.role !== "admin" ? (
            <p className="text-sm text-muted-foreground">Only an admin can decide this.</p>
          ) : (
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="comment">Comment (required to reject or request changes)</FieldLabel>
                <Textarea id="comment" rows={3} value={comment}
                  onChange={(e) => setComment(e.target.value)} />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button disabled={!canDecide || !!busy} onClick={() => decide("approve")}>
                  {busy === "approve" ? "Approving…" : "Approve"}
                </Button>
                <Button variant="outline" disabled={!canDecide || !!busy}
                  onClick={() => decide("request_changes")}>Request changes</Button>
                <Button variant="destructive" disabled={!canDecide || !!busy}
                  onClick={() => decide("reject")}>Reject</Button>
              </div>
            </FieldGroup>
          )}
        </Card>
      )}

      {data.result && (
        <Card title="Result">
          <pre className="overflow-x-auto text-xs">{JSON.stringify(data.result, null, 2)}</pre>
        </Card>
      )}
    </div>
  );
}

function Queue() {
  const params = useSearchParams();
  const [tab, setTab] = useState("pending");
  const [selected, setSelected] = useState<number | null>(
    params.get("id") ? Number(params.get("id")) : null,
  );
  const { data, error, loading, reload } = useApi<Approval[]>(
    tab === "all" ? "/approvals" : `/approvals?status=${tab}`,
  );
  const sel = selected ?? data?.[0]?.id ?? null;

  return (
    <div className="space-y-5">
      <Tabs value={tab} onValueChange={(v) => { setTab(String(v)); setSelected(null); }} className="gap-4">
        <PageHeader
          title="Actions"
          subtitle="Nothing consequential happens without a second admin approving it. The Copilot and workflows can only propose."
          actions={
            <TabsList className="rounded-full">
              <TabsTrigger value="pending" className="rounded-full">Pending</TabsTrigger>
              <TabsTrigger value="executed" className="rounded-full">Done</TabsTrigger>
              <TabsTrigger value="all" className="rounded-full">All</TabsTrigger>
            </TabsList>
          }
        />
        <TabsContent value={tab} className="mt-4">
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <div className="space-y-2">
              <Loading error={error} loading={loading && !data} />
              {data?.length === 0 && (
                <p className="text-sm text-muted-foreground">Nothing here.</p>
              )}
              {data?.map((a) => (
                <button key={a.id} onClick={() => setSelected(a.id)}
                  className={cn(
                    "w-full rounded-2xl bg-card p-3.5 text-left text-sm shadow-sm ring-1 ring-black/5 transition-colors hover:bg-muted/40 dark:ring-white/10",
                    sel === a.id && "bg-neutral-900 text-white ring-0 hover:bg-neutral-900 dark:bg-neutral-100 dark:text-neutral-900",
                  )}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{a.summary}</span>
                    <Badge variant="outline" className={cn("shrink-0", STATUS_STYLE[a.status], sel === a.id && "border-white/20 text-white dark:border-neutral-900/20 dark:text-neutral-900")}>
                      {label(a.status)}
                    </Badge>
                  </div>
                  <div className={cn("mt-1 text-xs text-muted-foreground", sel === a.id && "text-white/70 dark:text-neutral-900/70")}>
                    {label(a.action)} · {a.requested_by} · {new Date(a.created_at).toLocaleDateString()}
                  </div>
                </button>
              ))}
            </div>
            <div>
              {sel ? (
                <Detail id={sel} onDecided={reload} />
              ) : (
                <p className="text-sm text-muted-foreground">Pick a request to see what it would do.</p>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function ActionsPage() {
  return (
    <Suspense fallback={null}>
      <Queue />
    </Suspense>
  );
}
