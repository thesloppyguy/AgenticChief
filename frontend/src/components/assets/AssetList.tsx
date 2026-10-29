"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, Loading } from "@/components/ui";
import { api, getClaims } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { type AssetSummary, type Kind, TEMPLATES } from "./types";

const LIFE: Record<string, string> = {
  published: "bg-emerald-50 text-emerald-800 ring-emerald-200", validated: "bg-blue-50 text-blue-800 ring-blue-200",
  draft: "bg-slate-50 text-slate-700 ring-slate-300", update_pending: "bg-amber-50 text-amber-800 ring-amber-200", deprecated: "bg-slate-100 text-slate-500 ring-slate-300",
};
export const Life = ({ v }: { v: string }) => <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${LIFE[v] ?? ""}`}>{v.replace("_", " ")}</span>;

export default function AssetList({ kind }: { kind: Kind }) {
  const me = getClaims();
  const canAuthor = (me?.role === "admin" || me?.role === "editor") && me.companies === null;
  const { data, error, loading, reload } = useApi<AssetSummary[]>(`/${kind}s`);
  const [f, setF] = useState({ key: "", name: "", description: "", definition: JSON.stringify(TEMPLATES[kind], null, 2) });
  const [msg, setMsg] = useState<string | null>(null);
  const plural = kind === "skill" ? "Skills" : "Agents";

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      await api(`/${kind}s`, { method: "POST", body: JSON.stringify({ key: f.key, name: f.name, description: f.description, definition: JSON.parse(f.definition) }) });
      setMsg(`Draft created. Open it to validate and publish.`);
      reload();
    } catch (err) { setMsg(err instanceof SyntaxError ? "The definition is not valid JSON." : err instanceof Error ? err.message : "Failed"); }
  }
  const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";
  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">{plural}</h1>
      <p className="text-sm text-slate-600">
        {kind === "skill" ? "A skill is a reusable task: typed inputs, the tools it may use, and instructions. Run one with a few clicks."
          : "An agent is a specialist: its own instructions, tools and model. Pick one in Ask Copilot."}{" "}
        New ones start as drafts, are validated, and go live only after a second admin approves.
      </p>
      <Loading error={error} loading={loading && !data} />
      <ul className="grid gap-3 md:grid-cols-2">
        {data?.map((a) => (
          <li key={a.key} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-2"><Link href={`/${kind}s/${a.key}`} className="font-medium hover:underline">{a.name}</Link><Life v={a.lifecycle} /></div>
            <p className="mt-1 text-sm text-slate-600">{a.description}</p>
            <p className="mt-2 text-xs text-slate-500">{a.builtin ? "Built in · " : ""}tools: {a.tools.join(", ") || "none"}</p>
          </li>))}
        {data?.length === 0 && <li className="text-sm text-slate-500">None yet.</li>}
      </ul>
      {canAuthor && (
        <Card title={`New ${kind}`}>
          <form onSubmit={create} className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <label>Key (letters, digits, underscores)<input required value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} className={input} /></label>
              <label>Name<input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className={input} /></label>
            </div>
            <label className="block">Description<input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} className={input} /></label>
            <label className="block">Definition (JSON)<textarea rows={12} value={f.definition} onChange={(e) => setF({ ...f, definition: e.target.value })} className={`${input} font-mono text-xs`} /></label>
            {msg && <p role="status" className="text-slate-700">{msg}</p>}
            <button className="rounded bg-slate-900 px-3 py-1.5 text-white">Create draft</button>
          </form>
        </Card>)}
    </div>
  );
}
