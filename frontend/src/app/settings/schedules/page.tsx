"use client";
import { useState } from "react";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Sched {
  id: number; job: "ingest" | "monthly_review"; name: string; cadence: { type: string; time: string; weekday?: number; day?: number };
  params: { period?: string }; enabled: boolean; next_run_at: string; last_run_at: string | null; last_status: string | null; last_detail: string | null; running: boolean;
}
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const JOB = { ingest: "Load data from all sources", monthly_review: "Generate the monthly leadership review" };
const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";

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
      <p className="text-sm text-slate-600">Run jobs on a timetable without anyone clicking. Times are UTC. A scheduled review is only generated: publishing it still needs a second admin&apos;s approval. This process runs the schedule, so keep one API instance.</p>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>{msg.text}</p>}
      <Loading error={error} loading={loading && !data} />
      <ul className="space-y-3">
        {data?.map((s) => (
          <li key={s.id} className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><strong>{s.name}</strong> <span className="text-slate-500">· {JOB[s.job]}{s.params.period ? ` (${s.params.period} period)` : ""}</span>
                <div className="text-slate-600">{describe(s.cadence)} · {s.enabled ? `next ${new Date(s.next_run_at).toLocaleString()}` : "paused"}{s.running ? " · running now" : ""}</div>
                {s.last_run_at && <div className={s.last_status === "failed" ? "text-red-700" : "text-slate-600"}>Last run {new Date(s.last_run_at).toLocaleString()}: {s.last_status}{s.last_detail ? ` — ${s.last_detail}` : ""}</div>}</div>
              <div className="flex gap-3 text-xs">
                <button disabled={busy === s.id} className="underline" onClick={() => act(s.id, () => api(`/schedules/${s.id}/run-now`, { method: "POST" }), "Ran it now.")}>Run now</button>
                <button className="underline" onClick={() => act(s.id, () => api(`/schedules/${s.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !s.enabled }) }), s.enabled ? "Paused." : "Resumed.")}>{s.enabled ? "Pause" : "Resume"}</button>
                <button className="text-red-800 underline" onClick={() => window.confirm(`Delete “${s.name}”?`) && act(s.id, () => api(`/schedules/${s.id}`, { method: "DELETE" }), "Deleted.")}>Delete</button>
              </div>
            </div>
          </li>))}
        {data?.length === 0 && <li className="text-sm text-slate-500">No schedules yet.</li>}
      </ul>
      <Card title="New schedule">
        <form onSubmit={create} className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <label>Job<select value={f.job} onChange={(e) => setF({ ...f, job: e.target.value, period: e.target.value === "ingest" ? "current" : "previous" })} className={input}>{Object.entries(JOB).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label>Name<input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className={input} /></label>
            <label>Period<select value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })} className={input}><option value="current">This month</option><option value="previous">Last month</option></select></label>
            <label>How often<select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })} className={input}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
            {f.type === "weekly" && <label>Weekday<select value={f.weekday} onChange={(e) => setF({ ...f, weekday: e.target.value })} className={input}>{DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>}
            {f.type === "monthly" && <label>Day of month (1–28)<input type="number" min={1} max={28} value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} className={input} /></label>}
            <label>Time (UTC)<input type="time" required value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} className={input} /></label>
          </div>
          <button className="rounded bg-slate-900 px-3 py-1.5 text-white">Create schedule</button>
        </form>
      </Card>
    </div>
  );
}
