"use client";
import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ActionDef, Approval } from "@/lib/types";

const STATUS: Record<string, string> = {
  pending: "border-warning/30 bg-warning/10 text-warning", executed: "border-success/30 bg-success/10 text-success",
  approved: "border-success/30 bg-success/10 text-success", rejected: "bg-muted text-muted-foreground",
  denied: "border-destructive/30 bg-destructive/10 text-destructive", failed: "border-destructive/30 bg-destructive/10 text-destructive",
  changes_requested: "bg-secondary text-secondary-foreground",
};
const Pill = ({ s }: { s: string }) => (
  <Badge variant="outline" className={cn(STATUS[s])}>{label(s)}</Badge>
);

const ALL = "all";  // Select values cannot be empty; maps to "no filter"

function Detail({ id, onChange }: { id: number; onChange: () => void }) {
  const { data, error, loading, reload } = useApi<Approval>(`/approvals/${id}`);
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function decide(decision: string) {
    setMsg(null);
    try {
      await api(`/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, comment: comment || null }) });
      setComment(""); reload(); onChange();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <Card title={`Request #${id}`}>
      <Loading error={error} loading={loading} />
      {data && (
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2"><Pill s={data.status} /><span className="font-medium">{data.summary}</span></div>
          <dl className="grid grid-cols-2 gap-2">
            <div><dt className="text-muted-foreground">Requested by</dt><dd>{data.requested_by}{data.via === "copilot" ? " (via Copilot)" : ""}</dd></div>
            <div><dt className="text-muted-foreground">Risk</dt><dd>{label(data.risk)}</dd></div>
          </dl>
          {data.context?.reason && <p><span className="text-muted-foreground">Reason: </span>{data.context.reason}</p>}
          <div><div className="text-xs text-muted-foreground">Arguments</div>
            <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs">{JSON.stringify(data.args, null, 2)}</pre></div>
          {data.context && Object.keys(data.context).filter((k) => k !== "reason").length > 0 && (
            <div><div className="text-xs text-muted-foreground">What you are approving (checked by the server)</div>
              <pre className="overflow-x-auto rounded-md border border-warning/30 bg-warning/10 p-2 text-xs">{JSON.stringify(Object.fromEntries(Object.entries(data.context).filter(([k]) => k !== "reason")), null, 2)}</pre></div>
          )}
          {data.decision_comment && <p><span className="text-muted-foreground">Comment: </span>{data.decision_comment}</p>}
          {data.result && <p><span className="text-muted-foreground">Result: </span><code>{JSON.stringify(data.result)}</code></p>}
          {data.status === "pending" && (
            <div className="space-y-2">
              <Separator />
              <div className="space-y-1 pt-1">
                <Label htmlFor={`comment-${id}`}>Comment (required to reject or request changes)</Label>
                <Input id={`comment-${id}`} value={comment} onChange={(e) => setComment(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <Button onClick={() => decide("approve")}>Approve and run</Button>
                <Button variant="outline" onClick={() => decide("request_changes")}>Request changes</Button>
                <Button variant="destructive" onClick={() => decide("reject")}>Reject</Button>
              </div>
              <p className="text-xs text-muted-foreground">Only admins can decide, and not on their own requests. The server enforces both.</p>
            </div>
          )}
          {msg && <Alert variant="destructive"><AlertDescription>{msg}</AlertDescription></Alert>}
          <Separator />
          <ol className="text-xs text-muted-foreground">
            {data.events?.map((e, i) => (
              <li key={i}>{new Date(e.at).toLocaleString()} · {e.actor} · {label(e.event)}{e.comment ? ` — ${e.comment}` : ""}</li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}

function NewRequest({ onCreated }: { onCreated: (id: number) => void }) {
  const [period] = usePeriod();
  const actions = useApi<ActionDef[]>("/approvals/actions");
  const [action, setAction] = useState("send_kpi_reminder");
  const [codes, setCodes] = useState("");
  const [kpi, setKpi] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const args: Record<string, unknown> = { period };
    if (action === "send_kpi_reminder") {
      args.company_codes = codes.split(",").map((c) => c.trim()).filter(Boolean);
      if (kpi) args.kpi_key = kpi;
      if (note) args.note = note;
    }
    try {
      const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", { method: "POST", body: JSON.stringify({ action, args }) });
      setMsg(r.verdict === "deny" ? { ok: false, text: `Denied by policy: ${r.reason}` } : { ok: true, text: "Submitted for approval." });
      onCreated(r.approval.id);
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
  }
  const actionItems = (actions.data ?? []).map((a) => ({ value: a.key, label: label(a.key) }));
  return (
    <Card title="New request">
      <form onSubmit={submit} className="space-y-3 text-sm">
        <div className="space-y-1">
          <Label htmlFor="action">Action</Label>
          <Select items={actionItems} value={action} onValueChange={(v) => v != null && setAction(v)}>
            <SelectTrigger id="action" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {actionItems.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <p className="text-xs text-muted-foreground">{actions.data?.find((a) => a.key === action)?.description} Period: {period}.</p>
        {action === "send_kpi_reminder" && (
          <>
            <div className="space-y-1">
              <Label htmlFor="codes">Company codes (comma-separated, max 5)</Label>
              <Input id="codes" required value={codes} onChange={(e) => setCodes(e.target.value)} placeholder="IC001, IC002" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="kpi">KPI (optional key, e.g. kra_submission)</Label>
              <Input id="kpi" value={kpi} onChange={(e) => setKpi(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="note">Note (optional)</Label>
              <Input id="note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          </>
        )}
        {msg && (
          <Alert role={msg.ok ? "status" : "alert"} variant={msg.ok ? "default" : "destructive"} className={cn(msg.ok && "text-success")}>
            <AlertDescription className={cn(msg.ok && "text-success")}>{msg.text}</AlertDescription>
          </Alert>
        )}
        <Button type="submit">Submit</Button>
      </form>
    </Card>
  );
}

function Inner() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState("");
  const list = useApi<Approval[]>(`/approvals${status ? `?status=${status}` : ""}`);
  const statusItems = [{ value: ALL, label: "All" }, ...Object.keys(STATUS).map((s) => ({ value: s, label: label(s) }))];
  const selected = params.get("id") ? Number(params.get("id")) : null;

  return (
    <div className="grid max-w-6xl gap-6 md:grid-cols-2">
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Approvals</h1>
        <Card title="Requests"
          action={
            <Select items={statusItems} value={status || ALL} onValueChange={(v) => v != null && setStatus(v === ALL ? "" : v)}>
              <SelectTrigger aria-label="Filter by status"><SelectValue /></SelectTrigger>
              <SelectContent>
                {statusItems.map((i) => <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>)}
              </SelectContent>
            </Select>
          }>
          <Loading error={list.error} loading={list.loading} />
          <ul className="divide-y text-sm">
            {list.data?.map((a) => (
              <li key={a.id}>
                <Button variant="ghost" onClick={() => router.replace(`/approvals?id=${a.id}`)} className={cn("h-auto w-full justify-between gap-2 py-2 text-left font-normal", a.id === selected && "bg-muted")}>
                  <span className="truncate">#{a.id} · {a.summary}</span><Pill s={a.status} />
                </Button>
              </li>
            ))}
            {list.data?.length === 0 && <li className="py-2 text-muted-foreground">No requests.</li>}
          </ul>
        </Card>
        <NewRequest onCreated={(id) => { list.reload(); router.replace(`/approvals?id=${id}`); }} />
      </div>
      <div className="pt-0 md:pt-11">{selected ? <Detail key={selected} id={selected} onChange={list.reload} /> : <p className="text-sm text-muted-foreground">Select a request to see its history.</p>}</div>
    </div>
  );
}

export default function Approvals() {
  return <Suspense fallback={null}><Inner /></Suspense>;
}
