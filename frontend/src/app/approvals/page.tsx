"use client";
import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ActionDef, Approval } from "@/lib/types";

const STATUS: Record<string, string> = {
  pending: "bg-amber-50 text-amber-800 ring-amber-200", executed: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  approved: "bg-emerald-50 text-emerald-800 ring-emerald-200", rejected: "bg-slate-100 text-slate-700 ring-slate-300",
  denied: "bg-red-50 text-red-800 ring-red-200", failed: "bg-red-50 text-red-800 ring-red-200",
  changes_requested: "bg-blue-50 text-blue-800 ring-blue-200",
};
const Pill = ({ s }: { s: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS[s] ?? ""}`}>{label(s)}</span>
);

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
            <div><dt className="text-slate-500">Requested by</dt><dd>{data.requested_by}{data.via === "copilot" ? " (via Copilot)" : ""}</dd></div>
            <div><dt className="text-slate-500">Risk</dt><dd>{label(data.risk)}</dd></div>
          </dl>
          {data.context?.reason && <p><span className="text-slate-500">Reason: </span>{data.context.reason}</p>}
          <div><div className="text-xs text-slate-500">Arguments</div>
            <pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(data.args, null, 2)}</pre></div>
          {data.context && Object.keys(data.context).filter((k) => k !== "reason").length > 0 && (
            <div><div className="text-xs text-slate-500">What you are approving (checked by the server)</div>
              <pre className="overflow-x-auto rounded bg-amber-50 p-2 text-xs">{JSON.stringify(Object.fromEntries(Object.entries(data.context).filter(([k]) => k !== "reason")), null, 2)}</pre></div>
          )}
          {data.decision_comment && <p><span className="text-slate-500">Comment: </span>{data.decision_comment}</p>}
          {data.result && <p><span className="text-slate-500">Result: </span><code>{JSON.stringify(data.result)}</code></p>}
          {data.status === "pending" && (
            <div className="space-y-2 border-t border-slate-100 pt-3">
              <label className="block">Comment (required to reject or request changes)
                <input value={comment} onChange={(e) => setComment(e.target.value)} className="mt-1 w-full rounded border border-slate-300 px-2 py-1" />
              </label>
              <div className="flex gap-2">
                <button onClick={() => decide("approve")} className="rounded bg-emerald-700 px-3 py-1.5 text-white">Approve and run</button>
                <button onClick={() => decide("request_changes")} className="rounded border border-slate-300 px-3 py-1.5">Request changes</button>
                <button onClick={() => decide("reject")} className="rounded border border-red-300 px-3 py-1.5 text-red-800">Reject</button>
              </div>
              <p className="text-xs text-slate-500">Only admins can decide, and not on their own requests. The server enforces both.</p>
            </div>
          )}
          {msg && <p role="alert" className="text-red-700">{msg}</p>}
          <ol className="border-t border-slate-100 pt-3 text-xs text-slate-600">
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
  const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1";
  return (
    <Card title="New request">
      <form onSubmit={submit} className="space-y-3 text-sm">
        <label className="block">Action
          <select value={action} onChange={(e) => setAction(e.target.value)} className={input}>
            {actions.data?.map((a) => <option key={a.key} value={a.key}>{label(a.key)}</option>)}
          </select>
        </label>
        <p className="text-xs text-slate-500">{actions.data?.find((a) => a.key === action)?.description} Period: {period}.</p>
        {action === "send_kpi_reminder" && (
          <>
            <label className="block">Company codes (comma-separated, max 5)<input required value={codes} onChange={(e) => setCodes(e.target.value)} placeholder="IC001, IC002" className={input} /></label>
            <label className="block">KPI (optional key, e.g. kra_submission)<input value={kpi} onChange={(e) => setKpi(e.target.value)} className={input} /></label>
            <label className="block">Note (optional)<input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} className={input} /></label>
          </>
        )}
        {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-emerald-700" : "text-red-700"}>{msg.text}</p>}
        <button className="rounded bg-slate-900 px-4 py-2 text-white">Submit</button>
      </form>
    </Card>
  );
}

function Inner() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState("");
  const list = useApi<Approval[]>(`/approvals${status ? `?status=${status}` : ""}`);
  const selected = params.get("id") ? Number(params.get("id")) : null;

  return (
    <div className="grid max-w-6xl gap-6 md:grid-cols-2">
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Approvals</h1>
        <Card title="Requests"
          action={
            <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm">
              <option value="">All</option>
              {Object.keys(STATUS).map((s) => <option key={s} value={s}>{label(s)}</option>)}
            </select>
          }>
          <Loading error={list.error} loading={list.loading} />
          <ul className="divide-y divide-slate-100 text-sm">
            {list.data?.map((a) => (
              <li key={a.id}>
                <button onClick={() => router.replace(`/approvals?id=${a.id}`)} className={`flex w-full items-center justify-between gap-2 py-2 text-left hover:bg-slate-50 ${a.id === selected ? "bg-slate-50" : ""}`}>
                  <span className="truncate">#{a.id} · {a.summary}</span><Pill s={a.status} />
                </button>
              </li>
            ))}
            {list.data?.length === 0 && <li className="py-2 text-slate-500">No requests.</li>}
          </ul>
        </Card>
        <NewRequest onCreated={(id) => { list.reload(); router.replace(`/approvals?id=${id}`); }} />
      </div>
      <div className="pt-0 md:pt-11">{selected ? <Detail key={selected} id={selected} onChange={list.reload} /> : <p className="text-sm text-slate-500">Select a request to see its history.</p>}</div>
    </div>
  );
}

export default function Approvals() {
  return <Suspense fallback={null}><Inner /></Suspense>;
}
