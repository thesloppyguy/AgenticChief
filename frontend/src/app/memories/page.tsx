"use client";
import { useState } from "react";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Mem { id: number; kind: string; domain: string; summary: string; pinned: boolean; created_at: string; session_id: number | null }
const KIND: Record<string, string> = { decision: "bg-blue-50 text-blue-800 ring-blue-200", initiative: "bg-violet-50 text-violet-800 ring-violet-200", advice: "bg-emerald-50 text-emerald-800 ring-emerald-200" };

export default function Memories() {
  const { data, error, loading, reload } = useApi<{ enabled: boolean; memories: Mem[] }>("/memories");
  const [err, setErr] = useState<string | null>(null);
  const act = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } };
  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Memories</h1>
      <p className="text-sm text-slate-600">
        After a conversation the Copilot may note a decision you made, an initiative you started or advice you accepted, and offer it in later sessions.
        Memories are private to you, fade after 90 days unless pinned, and are context only: the Copilot is told they may be out of date.
        Pure lookups and skill runs are never remembered.
      </p>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <Loading error={error} loading={loading && !data} />
      {data && (
        <Card title={data.enabled ? "Memory is on" : "Memory is off"}
          action={<button className="rounded border border-slate-300 px-3 py-1.5 text-sm" onClick={() => act(() => api("/memories/settings", { method: "PUT", body: JSON.stringify({ enabled: !data.enabled }) }))}>
            {data.enabled ? "Turn off" : "Turn on"}</button>}>
          <p className="text-sm text-slate-600">{data.enabled ? "New conversations can add memories." : "Nothing new is saved or used. Existing memories are kept but not shown to the Copilot."}</p>
        </Card>)}
      <Card title={`Remembered (${data?.memories.length ?? 0})`}
        action={!!data?.memories.length && <button className="text-sm text-red-800 underline" onClick={() => window.confirm("Forget everything the Copilot remembers about you?") && act(() => api("/memories", { method: "DELETE" }))}>Forget everything</button>}>
        <ul className="divide-y divide-slate-100 text-sm">
          {data?.memories.map((m) => (
            <li key={m.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${KIND[m.kind] ?? ""}`}>{m.kind}</span>
                {m.pinned && <span className="mr-2 text-xs text-slate-500">★ pinned</span>}
                <span>{m.summary}</span>
                <div className="mt-1 text-xs text-slate-500">{m.domain} · {new Date(m.created_at).toLocaleDateString()}</div>
              </div>
              <div className="flex shrink-0 gap-3 text-xs">
                <button className="underline" onClick={() => act(() => api(`/memories/${m.id}/pin`, { method: "POST" }))}>{m.pinned ? "Unpin" : "Pin"}</button>
                <button className="text-red-800 underline" onClick={() => act(() => api(`/memories/${m.id}`, { method: "DELETE" }))}>Forget</button>
              </div>
            </li>))}
          {data?.memories.length === 0 && <li className="py-3 text-slate-500">Nothing remembered yet.</li>}
        </ul>
      </Card>
    </div>
  );
}
