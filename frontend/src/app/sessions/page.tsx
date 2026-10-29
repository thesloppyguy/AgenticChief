"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, Loading } from "@/components/ui";
import PinButton from "@/components/PinButton";
import { useApi } from "@/lib/hooks";

interface Row { id: number; title: string; message_count: number; last_at: string }
interface Detail { id: number; title: string; messages: { role: string; content: string; tools: string[] | null; at: string }[]; approvals: { id: number; action: string; summary: string; status: string }[] }

export default function Sessions() {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const list = useApi<Row[]>(`/copilot/sessions${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`);
  const detail = useApi<Detail>(sel ? `/copilot/sessions/${sel}` : null);

  return (
    <div className="grid max-w-6xl gap-6 md:grid-cols-[22rem_1fr]">
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Sessions</h1>
        <input aria-label="Search sessions" placeholder="Search titles and messages…" value={q} onChange={(e) => setQ(e.target.value)}
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm" />
        <Loading error={list.error} loading={list.loading && !list.data} />
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white text-sm">
          {list.data?.map((s) => (
            <li key={s.id}>
              <button onClick={() => setSel(s.id)} className={`w-full px-3 py-2 text-left hover:bg-slate-50 ${s.id === sel ? "bg-slate-50" : ""}`}>
                <div className="truncate font-medium">{s.title}</div>
                <div className="text-xs text-slate-500">{s.message_count} messages · {new Date(s.last_at).toLocaleString()}</div>
              </button>
            </li>
          ))}
          {list.data?.length === 0 && <li className="px-3 py-3 text-slate-500">No sessions{q ? " match" : " yet"}.</li>}
        </ul>
      </div>
      <div className="pt-0 md:pt-11">
        {!sel ? <p className="text-sm text-slate-500">Select a session to read it.</p> : (
          <Card title={detail.data?.title ?? "Session"} action={detail.data && (
            <span className="flex items-center gap-3 text-sm"><PinButton kind="session" target={String(sel)} /><Link href={`/copilot?session=${sel}`} className="underline">Continue in Copilot</Link></span>)}>
            <Loading error={detail.error} loading={detail.loading && !detail.data} />
            {detail.data && (
              <div className="space-y-4 text-sm">
                {detail.data.approvals.length > 0 && (
                  <div className="rounded bg-amber-50 p-3"><div className="mb-1 text-xs font-medium uppercase text-amber-800">Approvals filed from this session</div>
                    <ul>{detail.data.approvals.map((a) => <li key={a.id}><Link href={`/approvals?id=${a.id}`} className="underline">#{a.id} · {a.summary}</Link> <span className="text-slate-600">({a.status})</span></li>)}</ul></div>
                )}
                {detail.data.messages.map((m, i) => (
                  <div key={i} className={m.role === "user" ? "text-right" : ""}>
                    <div className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-lg px-3 py-2 text-left ${m.role === "user" ? "bg-slate-900 text-white" : "bg-slate-100"}`}>{m.content}</div>
                    <div className="mt-1 text-xs text-slate-500">{new Date(m.at).toLocaleString()}{m.tools?.length ? ` · used ${[...new Set(m.tools)].join(", ")}` : ""}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
