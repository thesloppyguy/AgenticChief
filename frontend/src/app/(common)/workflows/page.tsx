"use client";
import { useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, getClaims } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type {
  Cadence, CompanyCard, Scorecard, Watch, WatchTest, WorkflowDef, WorkflowDraft,
} from "@/lib/types";

const PILLARS = [
  "talent_acquisition", "performance_management", "learning_development",
  "organizational_effectiveness", "talent_management", "engagement_wellness", "retention",
];
const LIFECYCLE_STYLE: Record<string, string> = {
  published: "border-success/30 bg-success/10 text-success",
  validated: "border-warning/30 bg-warning/10 text-warning",
  draft: "text-muted-foreground",
  update_pending: "border-warning/30 bg-warning/10 text-warning",
  deprecated: "border-destructive/30 bg-destructive/10 text-destructive",
};

const DAILY: Cadence = { type: "daily", time: "06:00" };

async function run<T>(fn: () => Promise<T>, ok: string, after?: () => void): Promise<T | null> {
  try {
    const out = await fn();
    toast.success(ok);
    after?.();
    return out;
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Failed");
    return null;
  }
}

// --- watches -------------------------------------------------------------------------------------

function WatchForm({ onSaved }: { onSaved: () => void }) {
  const companies = useApi<Scorecard>("/scorecard");
  const [f, setF] = useState({
    name: "", company_code: "", subject: "overall", pillar: PILLARS[0], kpi_key: "",
    comparator: "below", threshold: "80", value: "red", time: "06:00",
  });
  const [busy, setBusy] = useState(false);
  const numeric = f.subject !== "status";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const condition = {
      subject: f.subject,
      ...(f.subject === "pillar" ? { pillar: f.pillar } : {}),
      ...(f.subject === "kpi" ? { kpi_key: f.kpi_key } : {}),
      comparator: numeric ? f.comparator : "changes_to",
      ...(numeric ? { threshold: Number(f.threshold) } : { value: f.value }),
    };
    await run(() => api("/watches", {
      method: "POST",
      body: JSON.stringify({
        name: f.name, company_code: f.company_code || null, condition,
        cadence: { type: "daily", time: f.time },
      }),
    }), "Watch created.", () => { setF({ ...f, name: "" }); onSaved(); });
    setBusy(false);
  }

  return (
    <form onSubmit={submit}>
      <FieldGroup>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="wname">Name</FieldLabel>
            <Input id="wname" required value={f.name} placeholder="Retention at LTTS"
              onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field>
            <FieldLabel htmlFor="wscope">Scope</FieldLabel>
            <select id="wscope" value={f.company_code}
              onChange={(e) => setF({ ...f, company_code: e.target.value })}
              className="h-9 rounded-md border bg-transparent px-3 text-sm">
              <option value="">The Group</option>
              {companies.data?.companies.map((c: CompanyCard) => (
                <option key={c.code} value={c.code}>{c.code} — {c.name}</option>
              ))}
            </select>
          </Field>
          <Field>
            <FieldLabel htmlFor="wsubject">Watch</FieldLabel>
            <select id="wsubject" value={f.subject}
              onChange={(e) => setF({ ...f, subject: e.target.value })}
              className="h-9 rounded-md border bg-transparent px-3 text-sm">
              <option value="overall">Overall score</option>
              <option value="pillar">A pillar&apos;s score</option>
              <option value="kpi">One KPI&apos;s score</option>
              <option value="status">Status</option>
            </select>
          </Field>
          {f.subject === "pillar" && (
            <Field>
              <FieldLabel htmlFor="wpillar">Pillar</FieldLabel>
              <select id="wpillar" value={f.pillar}
                onChange={(e) => setF({ ...f, pillar: e.target.value })}
                className="h-9 rounded-md border bg-transparent px-3 text-sm">
                {PILLARS.map((p) => <option key={p} value={p}>{label(p)}</option>)}
              </select>
            </Field>
          )}
          {f.subject === "kpi" && (
            <Field>
              <FieldLabel htmlFor="wkpi">KPI key</FieldLabel>
              <Input id="wkpi" required value={f.kpi_key} placeholder="overall_retention"
                onChange={(e) => setF({ ...f, kpi_key: e.target.value })} />
            </Field>
          )}
          {numeric ? (
            <>
              <Field>
                <FieldLabel htmlFor="wcomp">Fires when it is</FieldLabel>
                <select id="wcomp" value={f.comparator}
                  onChange={(e) => setF({ ...f, comparator: e.target.value })}
                  className="h-9 rounded-md border bg-transparent px-3 text-sm">
                  <option value="below">below</option>
                  <option value="above">above</option>
                </select>
              </Field>
              <Field>
                <FieldLabel htmlFor="wthresh">Threshold</FieldLabel>
                <Input id="wthresh" type="number" min={0} max={1000} step="0.1" required
                  value={f.threshold} onChange={(e) => setF({ ...f, threshold: e.target.value })} />
              </Field>
            </>
          ) : (
            <Field>
              <FieldLabel htmlFor="wvalue">Fires when it changes to</FieldLabel>
              <select id="wvalue" value={f.value}
                onChange={(e) => setF({ ...f, value: e.target.value })}
                className="h-9 rounded-md border bg-transparent px-3 text-sm">
                <option value="red">Off track (red)</option>
                <option value="amber">Needs attention (amber)</option>
                <option value="green">On track (green)</option>
              </select>
            </Field>
          )}
          <Field>
            <FieldLabel htmlFor="wtime">Check daily at (UTC)</FieldLabel>
            <Input id="wtime" type="time" value={f.time}
              onChange={(e) => setF({ ...f, time: e.target.value })} />
          </Field>
        </div>
        <p className="text-xs text-muted-foreground">
          A score is watched with <em>below</em> or <em>above</em>; a status with <em>changes to</em>,
          which fires only on the transition. A KPI with no value never fires — no data is not a breach.
        </p>
        <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create watch"}</Button>
      </FieldGroup>
    </form>
  );
}

function Watches() {
  const { data, error, loading, reload } = useApi<Watch[]>("/watches");
  const [tested, setTested] = useState<Record<number, WatchTest>>({});

  return (
    <div className="space-y-4">
      <Card title="Your watches">
        <p className="mb-3 text-sm text-muted-foreground">
          A watch checks one condition on a schedule and alerts you — only you — when it breaches.
          At most one alert per watch per period.
        </p>
        <Loading error={error} loading={loading && !data} />
        {data?.length === 0 && <p className="text-sm text-muted-foreground">No watches yet.</p>}
        <ul className="divide-y">
          {data?.map((w) => (
            <li key={w.id} className="py-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{w.name}</span>
                    {!w.enabled && <Badge variant="outline">Paused</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {w.company_code ?? "Group"} · {w.describes} · {w.cadence?.type} at {w.cadence?.time} UTC
                    {w.last_status && ` · last run ${w.last_status}`}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="sm"
                    onClick={() => run(() => api<WatchTest>(`/watches/${w.id}/test`, { method: "POST" }),
                      "Checked.").then((t) => t && setTested({ ...tested, [w.id]: t }))}>
                    Test
                  </Button>
                  <Button variant="ghost" size="sm"
                    onClick={() => run(() => api(`/watches/${w.id}`, {
                      method: "PATCH", body: JSON.stringify({ enabled: !w.enabled }),
                    }), w.enabled ? "Paused." : "Resumed.", reload)}>
                    {w.enabled ? "Pause" : "Resume"}
                  </Button>
                  <Button variant="ghost" size="sm" className="text-destructive"
                    onClick={() => window.confirm(`Delete "${w.name}"?`) &&
                      run(() => api(`/watches/${w.id}`, { method: "DELETE" }), "Deleted.", reload)}>
                    Delete
                  </Button>
                </div>
              </div>
              {tested[w.id] && (
                <p className={cn("mt-2 rounded border px-2 py-1 text-xs",
                  tested[w.id].would_fire
                    ? "border-destructive/30 bg-destructive/10 text-destructive"
                    : "border-success/30 bg-success/10 text-success")}>
                  {tested[w.id].would_fire ? "Would fire now" : "Not breached"} — observed{" "}
                  {tested[w.id].observed ?? "no value"}
                  {tested[w.id].previous != null && `, previously ${tested[w.id].previous}`}
                </p>
              )}
            </li>
          ))}
        </ul>
      </Card>
      <Card title="New watch"><WatchForm onSaved={reload} /></Card>
    </div>
  );
}

// --- workflow definitions -------------------------------------------------------------------------

function Builder({ onSaved }: { onSaved: () => void }) {
  const [period] = usePeriod();
  const [description, setDescription] = useState("");
  const [draft, setDraft] = useState<WorkflowDraft | null>(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  async function plan() {
    setBusy(true);
    const out = await run(() => api<WorkflowDraft>("/workflows/drafts", {
      method: "POST", body: JSON.stringify({ description, period }),
    }), "Planned. Review it before saving.");
    if (out) {
      setDraft(out);
      if (out.spec) setKey(out.spec.title.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40));
    }
    setBusy(false);
  }

  async function save() {
    if (!draft?.spec) return;
    setBusy(true);
    await run(() => api("/workflows/defs", {
      method: "POST",
      body: JSON.stringify({ key, name: draft.spec!.title, definition: draft.spec }),
    }), "Saved as a draft. Validate it, then propose publishing.", () => {
      setDraft(null);
      setDescription("");
      onSaved();
    });
    setBusy(false);
  }

  return (
    <Card title="Describe a workflow">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="desc">What should it do?</FieldLabel>
          <Textarea id="desc" rows={3} value={description}
            placeholder="Each month, build the group scorecard, find companies missing L&D data, and summarise what needs chasing."
            onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Button onClick={plan} disabled={busy || description.trim().length < 10}>
          <Sparkles className="size-4" />{busy ? "Planning…" : "Plan it"}
        </Button>
      </FieldGroup>

      {draft?.problems && draft.problems.length > 0 && (
        <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm">
          <p className="font-medium text-destructive">That plan is not valid</p>
          <ul className="mt-1 list-disc pl-5 text-destructive">
            {draft.problems.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
          {draft.raw && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs">What it produced</summary>
              <pre className="mt-1 overflow-x-auto text-xs">{draft.raw}</pre>
            </details>
          )}
        </div>
      )}

      {draft?.spec && (
        <div className="mt-4 space-y-3">
          <div>
            <h3 className="font-medium">{draft.spec.title}</h3>
            <ol className="mt-2 space-y-1 text-sm">
              {draft.spec.steps.map((s, i) => (
                <li key={s.key} className="flex gap-2">
                  <span className="text-muted-foreground tabular-nums">{i + 1}.</span>
                  <span>{s.label}</span>
                  <Badge variant="outline" className="text-[10px]">{s.type}</Badge>
                </li>
              ))}
            </ol>
          </div>
          <Field>
            <FieldLabel htmlFor="wfkey">Key</FieldLabel>
            <Input id="wfkey" value={key} onChange={(e) => setKey(e.target.value)} />
          </Field>
          <p className="text-xs text-muted-foreground">
            Saving creates a draft. It cannot run on a schedule until a second admin approves it.
          </p>
          <div className="flex gap-2">
            <Button onClick={save} disabled={busy || !key}>Save as draft</Button>
            <Button variant="outline" onClick={() => setDraft(null)}>Discard</Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function Definitions() {
  const [period] = usePeriod();
  const { data, error, loading, reload } = useApi<WorkflowDef[]>("/workflows/defs");
  const me = getClaims();

  return (
    <div className="space-y-4">
      <Card title="Saved workflows">
        <Loading error={error} loading={loading && !data} />
        {data?.length === 0 && (
          <p className="text-sm text-muted-foreground">None yet — describe one below.</p>
        )}
        <ul className="divide-y">
          {data?.map((w) => (
            <li key={w.key} className="py-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{w.title ?? w.name}</span>
                    <Badge variant="outline" className={cn(LIFECYCLE_STYLE[w.lifecycle])}>
                      {label(w.lifecycle)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">v{w.version}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {w.steps.length} steps
                    {w.uses.length > 0 && ` · reaches ${w.uses.join(", ")}`}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-1">
                  <Button variant="ghost" size="sm"
                    onClick={() => run(() => api(`/workflows/defs/${w.key}/validate`, { method: "POST" }),
                      "Validated.", reload)}>Validate</Button>
                  {me?.role === "admin" && w.published_version !== w.version && (
                    <Button variant="ghost" size="sm"
                      onClick={() => run(() => api("/approvals", {
                        method: "POST",
                        body: JSON.stringify({ action: "publish_asset", args: { asset_id: w.id } }),
                      }), "Proposed — a second admin must approve it.")}>Propose publishing</Button>
                  )}
                  {w.published_version && (
                    <Button variant="outline" size="sm"
                      onClick={() => run(() => api(`/workflows/defs/${w.key}/runs`, {
                        method: "POST", body: JSON.stringify({ period }),
                      }), `Running for ${period}.`)}>Run now</Button>
                  )}
                </div>
              </div>
              {w.validation && !w.validation.ok && (
                <ul className="mt-2 list-disc pl-5 text-xs text-destructive">
                  {w.validation.checks.filter((c) => !c.ok).map((c) => (
                    <li key={c.name}>{c.name}: {c.detail}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </Card>
      <Builder onSaved={reload} />
    </div>
  );
}

// --- page ------------------------------------------------------------------------------------------

export default function WorkflowsPage() {
  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Workflows</h1>
        <p className="text-sm text-muted-foreground">
          Repeatable work the platform runs for you. Anything consequential is still only ever proposed.
        </p>
      </div>
      <Tabs defaultValue="workflows">
        <TabsList>
          <TabsTrigger value="workflows">Workflows</TabsTrigger>
          <TabsTrigger value="watches">Watches</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
        </TabsList>
        <TabsContent value="workflows" className="mt-4"><Definitions /></TabsContent>
        <TabsContent value="watches" className="mt-4"><Watches /></TabsContent>
        <TabsContent value="runs" className="mt-4">
          <p className="text-sm text-muted-foreground">
            Every run, including the monthly review, is listed on{" "}
            <Link href="/reports" className="underline">Reports</Link>.
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
