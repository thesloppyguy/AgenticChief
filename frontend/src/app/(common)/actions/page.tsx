"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Loading, PageHeader } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
  });
}

function shortDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Turn common approval args into plain lines instead of a JSON dump. */
function ArgsSummary({ action, args }: { action: string; args: Record<string, unknown> }) {
  const rows: { label: string; value: string }[] = [];

  if (typeof args.period === "string") rows.push({ label: "Period", value: args.period });
  if (Array.isArray(args.company_codes) && args.company_codes.length) {
    rows.push({
      label: args.company_codes.length === 1 ? "Company" : "Companies",
      value: args.company_codes.map(String).join(", "),
    });
  }
  if (typeof args.kpi_key === "string" && args.kpi_key) {
    rows.push({ label: "KPI", value: label(args.kpi_key) });
  }
  if (typeof args.note === "string" && args.note.trim()) {
    rows.push({ label: "Note", value: args.note.trim() });
  }
  if (typeof args.subject === "string" && args.subject.trim()) {
    rows.push({ label: "Subject", value: args.subject.trim() });
  }
  if (typeof args.body === "string" && args.body.trim()) {
    rows.push({ label: "Message", value: args.body.trim().slice(0, 280) });
  }
  if (Array.isArray(args.recipient_emails) && args.recipient_emails.length) {
    rows.push({
      label: "Recipients",
      value: args.recipient_emails.map(String).join(", "),
    });
  }
  if (typeof args.program_key === "string") {
    rows.push({ label: "Programme", value: args.program_key });
  }
  if (typeof args.report_key === "string") {
    rows.push({ label: "Report", value: args.report_key });
  }
  if (typeof args.company_code === "string") {
    rows.push({ label: "IC", value: args.company_code });
  }
  if (typeof args.run_id === "number") {
    rows.push({ label: "Report run", value: `#${args.run_id}` });
  }
  if (typeof args.version === "number") {
    rows.push({ label: "Config version", value: String(args.version) });
  }

  const known = new Set([
    "period",
    "company_codes",
    "kpi_key",
    "note",
    "run_id",
    "version",
    "subject",
    "body",
    "recipient_emails",
    "program_key",
    "report_key",
    "company_code",
    "person_ids",
    "channel",
    "enrol_count",
    "mobility_count",
    "successor_count",
    "mentor_count",
    "at_risk_count",
    "cadence",
    "name",
  ]);
  const extras = Object.entries(args).filter(([k]) => !known.has(k));

  if (!rows.length && !extras.length) {
    return <p className="text-sm text-muted-foreground">No parameters.</p>;
  }

  return (
    <div className="space-y-3">
      {rows.length > 0 && (
        <dl className="space-y-2.5">
          {rows.map((r) => (
            <div key={r.label} className="flex flex-col gap-0.5 sm:flex-row sm:gap-6">
              <dt className="w-28 shrink-0 text-sm text-muted-foreground">{r.label}</dt>
              <dd className="text-sm text-foreground">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {extras.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            Technical details
          </summary>
          <pre className="mt-2 overflow-x-auto rounded-xl bg-muted/60 p-3 text-xs leading-relaxed">
            {JSON.stringify(
              action ? Object.fromEntries(extras) : args,
              null,
              2,
            )}
          </pre>
        </details>
      )}
    </div>
  );
}

function Detail({ id, onDecided }: { id: number; onDecided: () => void }) {
  const { data, error, loading, reload } = useApi<Approval>(`/approvals/${id}`);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const me = getClaims();

  if (!data) return <Loading error={error} loading={loading} />;

  const ownRequest = data.requested_by === me?.sub;
  const canDecide = me?.role === "admin" && data.status === "pending" && !ownRequest;
  const reason =
    data.context && typeof data.context === "object" && "reason" in data.context
      ? String((data.context as { reason?: unknown }).reason ?? "")
      : "";
  const otherContext =
    data.context && typeof data.context === "object"
      ? Object.fromEntries(
          Object.entries(data.context as Record<string, unknown>).filter(
            ([k]) => k !== "reason",
          ),
        )
      : {};

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
    <div className="overflow-hidden rounded-2xl bg-card shadow-sm ring-1 ring-black/5 dark:ring-white/10">
      <div className="space-y-4 border-b border-black/5 px-6 py-5 dark:border-white/10">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className={cn(STATUS_STYLE[data.status])}>
            {label(data.status)}
          </Badge>
          <span className="text-xs text-muted-foreground">{label(data.risk)}</span>
          <span className="text-xs text-muted-foreground">·</span>
          <span className="text-xs text-muted-foreground">#{data.id}</span>
        </div>
        <div className="space-y-1.5">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {data.summary}
          </h2>
          <p className="text-sm text-muted-foreground">
            {RISK_NOTE[data.risk] ?? label(data.action)}
          </p>
          <p className="text-xs text-muted-foreground">
            Requested by {data.requested_by}
            {data.via ? ` · ${data.via}` : ""} · {shortDateTime(data.created_at)}
          </p>
        </div>
      </div>

      <div className="space-y-6 px-6 py-5">
        <section className="space-y-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            What this would do
          </h3>
          {reason ? (
            <p className="text-sm leading-relaxed text-foreground">{reason}</p>
          ) : null}
          <ArgsSummary action={data.action} args={data.args ?? {}} />
          {Object.keys(otherContext).length > 0 && (
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                More context
              </summary>
              <dl className="mt-2 space-y-2 text-sm">
                {Object.entries(otherContext).map(([k, v]) => (
                  <div key={k} className="flex flex-col gap-0.5 sm:flex-row sm:gap-6">
                    <dt className="w-28 shrink-0 text-muted-foreground">{label(k)}</dt>
                    <dd className="break-words">
                      {typeof v === "string" ? (
                        v
                      ) : (
                        <code className="text-xs">{JSON.stringify(v)}</code>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </section>

        {data.events?.length ? (
          <section className="space-y-3">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              History
            </h3>
            <ol className="space-y-3 border-l border-black/10 pl-4 dark:border-white/10">
              {data.events.map((e, i) => (
                <li key={i} className="relative text-sm">
                  <span className="absolute -left-[1.15rem] top-1.5 size-1.5 rounded-full bg-muted-foreground/50" />
                  <div className="text-foreground">
                    {label(e.event)}
                    <span className="text-muted-foreground"> — {e.actor}</span>
                  </div>
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {shortDateTime(e.at)}
                  </div>
                  {e.comment ? (
                    <p className="mt-1 text-muted-foreground">“{e.comment}”</p>
                  ) : null}
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {data.result && (
          <section className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Result
            </h3>
            {typeof (data.result as { track?: unknown }).track === "string" && (
              <Link
                href={String((data.result as { track: string }).track)}
                className="text-sm font-medium text-primary hover:underline"
              >
                Open tracking (workflows / watches)
              </Link>
            )}
            {Array.isArray((data.result as { recipients?: unknown }).recipients) && (
              <p className="text-sm text-muted-foreground">
                Queued to{" "}
                {(
                  (data.result as { recipients: { name?: string; email?: string }[] })
                    .recipients
                )
                  .map((r) => r.name || r.email || "recipient")
                  .join(", ")}
              </p>
            )}
            <pre className="overflow-x-auto rounded-xl bg-muted/60 p-3 text-xs leading-relaxed">
              {JSON.stringify(data.result, null, 2)}
            </pre>
          </section>
        )}
      </div>

      {data.status === "pending" && (
        <div className="border-t border-black/5 bg-muted/20 px-6 py-5 dark:border-white/10">
          {ownRequest ? (
            <p className="text-sm text-muted-foreground">
              You asked for this, so you cannot approve it. A second admin must decide.
            </p>
          ) : me?.role !== "admin" ? (
            <p className="text-sm text-muted-foreground">Only an admin can decide this.</p>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="comment" className="text-sm font-medium text-foreground">
                  Comment
                </label>
                <p className="text-xs text-muted-foreground">
                  Required if you reject or ask for changes.
                </p>
                <Textarea
                  id="comment"
                  rows={2}
                  value={comment}
                  placeholder="Optional note for the requester…"
                  onChange={(e) => setComment(e.target.value)}
                  className="resize-none bg-background"
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button disabled={!canDecide || !!busy} onClick={() => decide("approve")}>
                  {busy === "approve" ? "Approving…" : "Approve"}
                </Button>
                <Button
                  variant="outline"
                  disabled={!canDecide || !!busy}
                  onClick={() => decide("request_changes")}
                >
                  Request changes
                </Button>
                <Button
                  variant="ghost"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  disabled={!canDecide || !!busy}
                  onClick={() => decide("reject")}
                >
                  Reject
                </Button>
              </div>
            </div>
          )}
        </div>
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
    <div className="space-y-6">
      <Tabs
        value={tab}
        onValueChange={(v) => {
          setTab(String(v));
          setSelected(null);
        }}
        className="gap-5"
      >
        <PageHeader
          title="Actions"
          subtitle="Approvals for reminders, snapshots, and other consequential changes."
          actions={
            <TabsList className="rounded-full">
              <TabsTrigger value="pending" className="rounded-full">
                Pending
              </TabsTrigger>
              <TabsTrigger value="executed" className="rounded-full">
                Done
              </TabsTrigger>
              <TabsTrigger value="all" className="rounded-full">
                All
              </TabsTrigger>
            </TabsList>
          }
        />
        <TabsContent value={tab} className="mt-0">
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
            <div className="space-y-2">
              <Loading error={error} loading={loading && !data} />
              {data?.length === 0 && (
                <div className="rounded-2xl bg-card px-4 py-10 text-center shadow-sm ring-1 ring-black/5 dark:ring-white/10">
                  <p className="text-sm text-muted-foreground">Nothing in this queue.</p>
                </div>
              )}
              {data?.map((a) => {
                const active = sel === a.id;
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setSelected(a.id)}
                    className={cn(
                      "w-full rounded-2xl px-4 py-3.5 text-left transition-colors",
                      "ring-1 ring-black/5 dark:ring-white/10",
                      active
                        ? "bg-neutral-900 text-white ring-0 dark:bg-neutral-100 dark:text-neutral-900"
                        : "bg-card text-foreground shadow-sm hover:bg-muted/40",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="line-clamp-2 text-sm font-medium leading-snug">
                        {a.summary}
                      </p>
                      {!active && (
                        <Badge
                          variant="outline"
                          className={cn("shrink-0 text-[10px]", STATUS_STYLE[a.status])}
                        >
                          {label(a.status)}
                        </Badge>
                      )}
                    </div>
                    <p
                      className={cn(
                        "mt-2 text-xs",
                        active
                          ? "text-white/65 dark:text-neutral-900/65"
                          : "text-muted-foreground",
                      )}
                    >
                      {label(a.action)}
                      <span className="mx-1.5 opacity-50">·</span>
                      {shortDate(a.created_at)}
                    </p>
                  </button>
                );
              })}
            </div>
            <div className="min-w-0">
              {sel ? (
                <Detail id={sel} onDecided={reload} />
              ) : (
                <div className="rounded-2xl bg-card px-6 py-16 text-center shadow-sm ring-1 ring-black/5 dark:ring-white/10">
                  <p className="text-sm text-muted-foreground">
                    Select a request to review it.
                  </p>
                </div>
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
