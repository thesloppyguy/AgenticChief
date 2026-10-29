"use client";
import { useState } from "react";
import Link from "next/link";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AlertItem, AlertPrefs, Approval } from "@/lib/types";

const SEV: Record<string, string> = {
  urgent: "border-destructive bg-destructive/10 text-destructive font-semibold", high: "border-destructive/40 text-destructive",
  medium: "border-warning/40 text-warning", low: "text-muted-foreground",
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
      {err && <Alert variant="destructive" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}

      {(pending.data?.length ?? 0) > 0 && (
        <Card title={`Approvals waiting (${pending.data!.length})`} action={<Link href="/approvals" className="text-sm underline">Open approvals</Link>}>
          <ul className="divide-y divide-border text-sm">
            {pending.data!.slice(0, 5).map((a) => (
              <li key={a.id} className="py-2"><Link href={`/approvals?id=${a.id}`} className="hover:underline">#{a.id} · {a.summary}</Link>
                <span className="ml-2 text-muted-foreground">from {a.requested_by}{a.via === "copilot" ? " via Copilot" : ""}</span></li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Alerts"
        action={
          <div className="flex items-center gap-3 text-sm">
            <Label htmlFor="unread-only" className="gap-1"><Checkbox id="unread-only" checked={unreadOnly} onCheckedChange={(c) => setUnreadOnly(c === true)} /> Unread only</Label>
            <Label htmlFor="show-hidden" className="gap-1"><Checkbox id="show-hidden" checked={showHidden} onCheckedChange={(c) => setShowHidden(c === true)} /> Include hidden by my settings</Label>
            <Button variant="outline" size="sm" onClick={() => act("/alerts/read-all")}>Mark all read</Button>
          </div>
        }>
        <Loading error={alerts.error} loading={alerts.loading} />
        <ul className="divide-y divide-border">
          {alerts.data?.map((a) => (
            <li key={a.id} className={`flex items-start justify-between gap-4 py-3 ${a.read ? "opacity-60" : ""}`}>
              <div className="min-w-0 text-sm">
                <Badge variant="outline" className={`mr-2 ${SEV[a.severity] ?? ""}`}>{a.severity}</Badge>
                <span className="font-medium">{a.title}</span>
                <div className="mt-1 text-xs text-muted-foreground">
                  {a.period}{a.detail?.synthetic ? " · synthetic data" : ""}
                  {a.detail?.weakest_pillars?.length ? ` · weakest: ${a.detail.weakest_pillars.map((p) => `${label(p.pillar)} ${p.score}`).join(", ")}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1 text-sm">
                {a.company_id != null && <Button variant="ghost" size="xs" render={<Link href={`/companies/${a.company_id}`} />}>View</Button>}
                {!a.read && <Button variant="ghost" size="xs" onClick={() => act(`/alerts/${a.id}/read`)}>Mark read</Button>}
              </div>
            </li>
          ))}
          {alerts.data?.length === 0 && <li className="py-3 text-sm text-muted-foreground">Nothing to show.</li>}
        </ul>
      </Card>

      <Card title="Alert settings" action={!pf && <Button variant="outline" size="sm" onClick={editPrefs}>Edit</Button>}>
        {saved && <Alert role="status" className="mb-2"><AlertDescription className="text-success">{saved}</AlertDescription></Alert>}
        {!pf && prefs.data && (
          <p className="text-sm">
            Show alerts of <strong>{prefs.data.min_severity}</strong> severity and above
            {prefs.data.muted_kinds.length ? <>, muting <strong>{prefs.data.muted_kinds.join(", ").replace(/_/g, " ")}</strong></> : ""}.{" "}
            {prefs.data.quiet_start ? <>Quiet hours {prefs.data.quiet_start}–{prefs.data.quiet_end} ({prefs.data.tz}): no pop-ups, except urgent.</> : "No quiet hours."}
          </p>)}
        {pf && prefs.data && (
          <form onSubmit={savePrefs} className="space-y-3 text-sm">
            <div className="space-y-1"><Label htmlFor="min-sev">Minimum severity</Label>
              <Select value={pf.min_severity} onValueChange={(v) => { if (v) setPf({ ...pf, min_severity: v }); }}>
                <SelectTrigger id="min-sev" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{prefs.data.severities.map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent>
              </Select></div>
            <fieldset><legend>Mute these kinds</legend>
              <div className="mt-1 flex flex-wrap gap-3">{prefs.data.known_kinds.map((k) => (
                <Label key={k} htmlFor={`mute-${k}`} className="gap-1"><Checkbox id={`mute-${k}`} checked={pf.muted.includes(k)} onCheckedChange={(c) => setPf({ ...pf, muted: c === true ? [...pf.muted, k] : pf.muted.filter((m) => m !== k) })} /> {k.replace(/_/g, " ")}</Label>))}</div></fieldset>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1"><Label htmlFor="q-start">Quiet from</Label><Input id="q-start" type="time" value={pf.start} onChange={(e) => setPf({ ...pf, start: e.target.value })} /></div>
              <div className="space-y-1"><Label htmlFor="q-end">Quiet until</Label><Input id="q-end" type="time" value={pf.end} onChange={(e) => setPf({ ...pf, end: e.target.value })} /></div>
              <div className="space-y-1"><Label htmlFor="q-tz">Timezone</Label><Input id="q-tz" value={pf.tz} onChange={(e) => setPf({ ...pf, tz: e.target.value })} /></div>
            </div>
            <p className="text-xs text-muted-foreground">Quiet hours only silence live pop-ups. Urgent alerts still come through, and nothing is hidden from this list because of them.</p>
            <div className="flex gap-2"><Button type="submit">Save</Button><Button type="button" variant="outline" onClick={() => setPf(null)}>Cancel</Button></div>
          </form>)}
      </Card>
    </div>
  );
}
