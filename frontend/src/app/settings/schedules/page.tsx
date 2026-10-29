"use client";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Sched {
  id: number; job: "ingest" | "monthly_review"; name: string; cadence: { type: string; time: string; weekday?: number; day?: number };
  params: { period?: string }; enabled: boolean; next_run_at: string; last_run_at: string | null; last_status: string | null; last_detail: string | null; running: boolean;
}
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const JOB = { ingest: "Load data from all sources", monthly_review: "Generate the monthly leadership review" };
const field = "flex flex-col items-start gap-1.5";
const PERIODS = { current: "This month", previous: "Last month" };
const TYPES = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" };
const WEEKDAYS = Object.fromEntries(DAYS.map((d, i) => [String(i), d]));

function Pick({ id, items, value, onChange }: { id: string; items: Record<string, string>; value: string; onChange: (v: string) => void }) {
  return (
    <Select items={items} value={value} onValueChange={(v) => { if (v != null) onChange(v); }}>
      <SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger>
      <SelectContent>{Object.entries(items).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
    </Select>
  );
}

const describe = (c: Sched["cadence"]) =>
  c.type === "daily" ? `Every day at ${c.time} UTC` : c.type === "weekly" ? `Every ${DAYS[c.weekday ?? 0]} at ${c.time} UTC` : `On day ${c.day} of each month at ${c.time} UTC`;

export default function Schedules() {
  const { data, error, loading, reload } = useApi<Sched[]>("/schedules");
  const [f, setF] = useState({ job: "ingest", name: "", type: "daily", time: "02:00", weekday: "0", day: "2", period: "current" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const cadence = { type: f.type, time: f.time, ...(f.type === "weekly" ? { weekday: Number(f.weekday) } : {}), ...(f.type === "monthly" ? { day: Number(f.day) } : {}) };
    try { await api("/schedules", { method: "POST", body: JSON.stringify({ job: f.job, name: f.name, cadence, params: { period: f.period } }) }); setMsg({ ok: true, text: "Schedule created." }); reload(); }
    catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
  }
  async function act(id: number, fn: () => Promise<unknown>, ok: string) {
    setBusy(id); setMsg(null);
    try { await fn(); setMsg({ ok: true, text: ok }); reload(); } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); } finally { setBusy(null); }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Schedules</h1>
      <p className="text-sm text-muted-foreground">Run jobs on a timetable without anyone clicking. Times are UTC. A scheduled review is only generated: publishing it still needs a second admin&apos;s approval. This process runs the schedule, so keep one API instance.</p>
      {msg && <Alert role={msg.ok ? "status" : "alert"} variant={msg.ok ? "default" : "destructive"} className={msg.ok ? "text-success" : undefined}><AlertDescription className={msg.ok ? "text-success" : undefined}>{msg.text}</AlertDescription></Alert>}
      <Loading error={error} loading={loading && !data} />
      <ul className="space-y-3">
        {data?.map((s) => (
          <li key={s.id} className="rounded-lg border bg-card p-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><strong>{s.name}</strong> <span className="text-muted-foreground">· {JOB[s.job]}{s.params.period ? ` (${s.params.period} period)` : ""}</span>
                <div className="text-muted-foreground">{describe(s.cadence)} · {s.enabled ? `next ${new Date(s.next_run_at).toLocaleString()}` : "paused"}{s.running ? " · running now" : ""}</div>
                {s.last_run_at && <div className={s.last_status === "failed" ? "text-destructive" : "text-muted-foreground"}>Last run {new Date(s.last_run_at).toLocaleString()}: {s.last_status}{s.last_detail ? ` — ${s.last_detail}` : ""}</div>}</div>
              <div className="flex gap-1">
                <Button variant="link" size="xs" disabled={busy === s.id} onClick={() => act(s.id, () => api(`/schedules/${s.id}/run-now`, { method: "POST" }), "Ran it now.")}>Run now</Button>
                <Button variant="link" size="xs" onClick={() => act(s.id, () => api(`/schedules/${s.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !s.enabled }) }), s.enabled ? "Paused." : "Resumed.")}>{s.enabled ? "Pause" : "Resume"}</Button>
                <Button variant="link" size="xs" className="text-destructive" onClick={() => window.confirm(`Delete “${s.name}”?`) && act(s.id, () => api(`/schedules/${s.id}`, { method: "DELETE" }), "Deleted.")}>Delete</Button>
              </div>
            </div>
          </li>))}
        {data?.length === 0 && <li className="text-sm text-muted-foreground">No schedules yet.</li>}
      </ul>
      <Card title="New schedule">
        <form onSubmit={create} className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <div className={field}><Label htmlFor="sch-job">Job</Label><Pick id="sch-job" items={JOB} value={f.job} onChange={(v) => setF({ ...f, job: v, period: v === "ingest" ? "current" : "previous" })} /></div>
            <div className={field}><Label htmlFor="sch-name">Name</Label><Input id="sch-name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
            <div className={field}><Label htmlFor="sch-period">Period</Label><Pick id="sch-period" items={PERIODS} value={f.period} onChange={(v) => setF({ ...f, period: v })} /></div>
            <div className={field}><Label htmlFor="sch-type">How often</Label><Pick id="sch-type" items={TYPES} value={f.type} onChange={(v) => setF({ ...f, type: v })} /></div>
            {f.type === "weekly" && <div className={field}><Label htmlFor="sch-weekday">Weekday</Label><Pick id="sch-weekday" items={WEEKDAYS} value={f.weekday} onChange={(v) => setF({ ...f, weekday: v })} /></div>}
            {f.type === "monthly" && <div className={field}><Label htmlFor="sch-day">Day of month (1–28)</Label><Input id="sch-day" type="number" min={1} max={28} value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} /></div>}
            <div className={field}><Label htmlFor="sch-time">Time (UTC)</Label><Input id="sch-time" type="time" required value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} /></div>
          </div>
          <Button type="submit">Create schedule</Button>
        </form>
      </Card>
    </div>
  );
}
