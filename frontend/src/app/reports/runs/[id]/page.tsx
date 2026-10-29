"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import ReportView from "@/components/ReportView";
import PinButton from "@/components/PinButton";
import { Card, Loading } from "@/components/ui";
import { API_URL, api, download, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Approval, RunDetail } from "@/lib/types";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading, reload } = useApi<RunDetail>(`/workflows/runs/${id}`);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null);
  const active = data?.status === "queued" || data?.status === "running";

  useEffect(() => {
    if (!active) return;
    const t = setInterval(reload, 1500);  // progress: poll while the run is working
    return () => clearInterval(t);
  }, [active, reload]);

  async function publish() {
    try {
      const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", {
        method: "POST", body: JSON.stringify({ action: "publish_monthly_report", args: { run_id: Number(id) } }),
      });
      setMsg(r.verdict === "deny" ? { ok: false, text: `Denied: ${r.reason}` }
        : { ok: true, text: "Sent for approval. A different admin must approve it.", href: `/approvals?id=${r.approval.id}` });
    } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" }); }
  }

  async function resume() {
    try { await api(`/workflows/runs/${id}/resume`, { method: "POST" }); reload(); }
    catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" }); }
  }

  async function download_md() {
    const res = await fetch(`${API_URL}/workflows/runs/${id}/markdown`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) return setMsg({ ok: false, text: "Download failed" });
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `monthly-review-${data?.period}.md` });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="max-w-5xl space-y-6">
      <Link href="/reports" className="text-sm text-slate-500 hover:underline">← Reports</Link>
      <Loading error={error} loading={loading && !data} />
      {data && (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h1 className="text-2xl font-semibold">Monthly review <span className="text-base font-normal text-slate-500">{data.period} · run #{data.id} · {data.status}</span></h1>
            <div className="flex gap-2 text-sm">
              <PinButton kind="run" target={id} />
              {data.status === "succeeded" && <>
                <button onClick={() => download(`/workflows/runs/${id}/pdf`, `monthly-review-${data.period}.pdf`).catch((e) => setMsg({ ok: false, text: e.message }))} className="rounded border border-slate-300 px-3 py-1.5">Download PDF</button>
                <button onClick={download_md} className="rounded border border-slate-300 px-3 py-1.5">Download Markdown</button>
                <button onClick={publish} className="rounded bg-slate-900 px-3 py-1.5 text-white">Propose publishing</button></>}
              {(data.status === "failed" || data.status === "interrupted") && <button onClick={resume} className="rounded bg-slate-900 px-3 py-1.5 text-white">Resume</button>}
            </div>
          </div>
          {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>
            {msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}</p>}
          {data.status !== "succeeded" && (
            <Card title="Progress">
              <ol className="space-y-1 text-sm">
                {data.steps.map((s) => (
                  <li key={s.key} className={s.done ? "text-emerald-800" : "text-slate-500"}>{s.done ? "✓" : "○"} {s.label}</li>
                ))}
              </ol>
              {data.error && <p role="alert" className="mt-3 text-sm text-red-700">Stopped with {data.error}. Finished steps are kept; Resume continues from the next one.</p>}
              {data.status === "interrupted" && <p className="mt-3 text-sm text-slate-600">The worker stopped. Resume continues from the last finished step.</p>}
            </Card>
          )}
          {data.result && <ReportView r={data.result} />}
        </>
      )}
    </div>
  );
}
