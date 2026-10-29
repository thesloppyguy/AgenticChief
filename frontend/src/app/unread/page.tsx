"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AlertItem, AlertPrefs, Approval } from "@/lib/types";

const SEV: Record<string, string> = {
  urgent: "bg-red-100 text-red-900 ring-red-300", high: "bg-red-50 text-red-800 ring-red-200",
  medium: "bg-amber-50 text-amber-800 ring-amber-200", low: "bg-slate-50 text-slate-600 ring-slate-200",
};

export default function Unread() {
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [showHidden, setShowHidden] = useState(false);
  const alerts = useApi<AlertItem[]>(`/alerts?unread_only=${unreadOnly}&include_hidden=${showHidden}`);
  const prefs = useApi<AlertPrefs>("/alert-prefs");
  const [pf, setPf] = useState<{ min_severity: string; muted: string[]; start: string; end: string; tz: string } | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  function editPrefs() {
    if (!prefs.data) return;
    setPf({ min_severity: prefs.data.min_severity, muted: prefs.data.muted_kinds, start: prefs.data.quiet_start ?? "", end: prefs.data.quiet_end ?? "",
      tz: prefs.data.tz === "UTC" && Intl.DateTimeFormat().resolvedOptions().timeZone ? Intl.DateTimeFormat().resolvedOptions().timeZone : prefs.data.tz });
  }
  async function savePrefs(e: React.FormEvent) {
    e.preventDefault();
    if (!pf) return;
    setErr(null); setSaved(null);
    try {
      const quiet = pf.start && pf.end ? { quiet_start: pf.start, quiet_end: pf.end } : {};
      await api("/alert-prefs", { method: "PUT", body: JSON.stringify({ min_severity: pf.min_severity, muted_kinds: pf.muted, tz: pf.tz, ...quiet }) });
      setSaved("Saved. Your open streams use the new settings straight away."); setPf(null); prefs.reload(); alerts.reload();
    } catch (er) { setErr(er instanceof Error ? er.message : "Failed"); }
  }
  const pending = useApi<Approval[]>("/approvals?status=pending");
  const [err, setErr] = useState<string | null>(null);

  async function act(path: string) {
    setErr(null);
    try { await api(path, { method: "POST" }); alerts.reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Unread</h1>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}

      {(pending.data?.length ?? 0) > 0 && (
        <Card title={`Approvals waiting (${pending.data!.length})`} action={<Link href="/approvals" className="text-sm underline">Open approvals</Link>}>
          <ul className="divide-y divide-slate-100 text-sm">
            {pending.data!.slice(0, 5).map((a) => (
              <li key={a.id} className="py-2"><Link href={`/approvals?id=${a.id}`} className="hover:underline">#{a.id} · {a.summary}</Link>
                <span className="ml-2 text-slate-500">from {a.requested_by}{a.via === "copilot" ? " via Copilot" : ""}</span></li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Alerts"
        action={
          <div className="flex items-center gap-3 text-sm">
            <label className="flex items-center gap-1"><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Unread only</label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Include hidden by my settings</label>
            <button onClick={() => act("/alerts/read-all")} className="underline">Mark all read</button>
          </div>
        }>
        <Loading error={alerts.error} loading={alerts.loading} />
        <ul className="divide-y divide-slate-100">
          {alerts.data?.map((a) => (
            <li key={a.id} className={`flex items-start justify-between gap-4 py-3 ${a.read ? "opacity-60" : ""}`}>
              <div className="min-w-0 text-sm">
                <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${SEV[a.severity]}`}>{a.severity}</span>
                <span className="font-medium">{a.title}</span>
                <div className="mt-1 text-xs text-slate-500">
                  {a.period}{a.detail?.synthetic ? " · synthetic data" : ""}
                  {a.detail?.weakest_pillars?.length ? ` · weakest: ${a.detail.weakest_pillars.map((p) => `${label(p.pillar)} ${p.score}`).join(", ")}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 gap-3 text-sm">
                {a.company_id != null && <Link className="underline" href={`/companies/${a.company_id}`}>View</Link>}
                {!a.read && <button className="underline" onClick={() => act(`/alerts/${a.id}/read`)}>Mark read</button>}
              </div>
            </li>
          ))}
          {alerts.data?.length === 0 && <li className="py-3 text-sm text-slate-500">Nothing to show.</li>}
        </ul>
      </Card>

      <Card title="Alert settings" action={!pf && <button className="text-sm underline" onClick={editPrefs}>Edit</button>}>
        {saved && <p role="status" className="mb-2 text-sm text-emerald-700">{saved}</p>}
        {!pf && prefs.data && (
          <p className="text-sm text-slate-700">
            Show alerts of <strong>{prefs.data.min_severity}</strong> severity and above
            {prefs.data.muted_kinds.length ? <>, muting <strong>{prefs.data.muted_kinds.join(", ").replace(/_/g, " ")}</strong></> : ""}.{" "}
            {prefs.data.quiet_start ? <>Quiet hours {prefs.data.quiet_start}–{prefs.data.quiet_end} ({prefs.data.tz}): no pop-ups, except urgent.</> : "No quiet hours."}
          </p>)}
        {pf && prefs.data && (
          <form onSubmit={savePrefs} className="space-y-3 text-sm">
            <label className="block">Minimum severity<select value={pf.min_severity} onChange={(e) => setPf({ ...pf, min_severity: e.target.value })} className="mt-1 w-full rounded border border-slate-300 px-2 py-1">
              {prefs.data.severities.map((x) => <option key={x}>{x}</option>)}</select></label>
            <fieldset><legend>Mute these kinds</legend>
              <div className="mt-1 flex flex-wrap gap-3">{prefs.data.known_kinds.map((k) => (
                <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={pf.muted.includes(k)} onChange={(e) => setPf({ ...pf, muted: e.target.checked ? [...pf.muted, k] : pf.muted.filter((m) => m !== k) })} /> {k.replace(/_/g, " ")}</label>))}</div></fieldset>
            <div className="grid grid-cols-3 gap-3">
              <label>Quiet from<input type="time" value={pf.start} onChange={(e) => setPf({ ...pf, start: e.target.value })} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" /></label>
              <label>Quiet until<input type="time" value={pf.end} onChange={(e) => setPf({ ...pf, end: e.target.value })} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" /></label>
              <label>Timezone<input value={pf.tz} onChange={(e) => setPf({ ...pf, tz: e.target.value })} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" /></label>
            </div>
            <p className="text-xs text-slate-500">Quiet hours only silence live pop-ups. Urgent alerts still come through, and nothing is hidden from this list because of them.</p>
            <div className="flex gap-2"><button className="rounded bg-slate-900 px-3 py-1.5 text-white">Save</button><button type="button" onClick={() => setPf(null)} className="rounded border border-slate-300 px-3 py-1.5">Cancel</button></div>
          </form>)}
      </Card>
    </div>
  );
}
