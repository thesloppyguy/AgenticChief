"use client";
import { useState } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import PinButton from "@/components/PinButton";
import { Card, Loading } from "@/components/ui";
import { api, getClaims } from "@/lib/api";
import { streamChat } from "@/lib/chat";
import { useApi } from "@/lib/hooks";
import { Life } from "./AssetList";
import type { Approval } from "@/lib/types";
import type { AssetDetail as Detail, InputSchema, Kind } from "./types";

const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";

function RunForm({ asset, kind }: { asset: Detail; kind: Kind }) {
  const [period] = usePeriod();
  const me = getClaims();
  const schema: InputSchema = asset.inputs ?? { type: "object", properties: {} };
  const [vals, setVals] = useState<Record<string, string | boolean>>(() => Object.fromEntries(
    Object.entries(schema.properties).map(([k, p]) => [k, k === "period" ? period : p.default !== undefined ? (p.default as string | boolean) : p.type === "boolean" ? false : ""])));
  const [draft, setDraft] = useState(false);
  const [out, setOut] = useState("");
  const [tools, setTools] = useState<string[]>([]);
  const [sid, setSid] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setOut(""); setTools([]); setErr(null); setSid(null);
    const inputs = Object.fromEntries(Object.entries(schema.properties).flatMap(([k, p]) => {
      const v = vals[k];
      if (v === "" || v === undefined) return [];
      return [[k, p.type === "integer" ? parseInt(String(v), 10) : p.type === "number" ? Number(v) : v]];
    }));
    await streamChat({ skill_key: asset.key, skill_inputs: inputs, period, allow_draft: draft }, {
      onChunk: (c) => setOut((o) => o + c), onTool: (n) => setTools((t) => [...t, n]),
      onError: setErr, onDone: setSid,
    });
    setBusy(false);
  }
  return (
    <Card title={`Run this ${kind}`}>
      <form onSubmit={run} className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(schema.properties).map(([k, p]) => (
            <label key={k} className={p.type === "boolean" ? "flex items-end gap-2" : "block"}>
              {k.replace(/_/g, " ")}{schema.required?.includes(k) ? " *" : ""}
              {p.enum ? <select value={String(vals[k])} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} className={input}>{p.enum.map((o) => <option key={o}>{o}</option>)}</select>
                : p.type === "boolean" ? <input type="checkbox" checked={!!vals[k]} onChange={(e) => setVals({ ...vals, [k]: e.target.checked })} />
                : k === "period" ? <input type="month" required value={String(vals[k])} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} className={input} />
                : <input type={p.type === "integer" || p.type === "number" ? "number" : "text"} min={p.minimum} max={p.maximum} required={schema.required?.includes(k)} value={String(vals[k])} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} className={input} />}
            </label>))}
        </div>
        {me?.role === "admin" && asset.published_version === null && <label className="flex items-center gap-2"><input type="checkbox" checked={draft} onChange={(e) => setDraft(e.target.checked)} /> Try the unpublished draft (admin)</label>}
        <button disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50">{busy ? "Running…" : "Run"}</button>
      </form>
      {err && <p role="alert" className="mt-3 text-sm text-red-700">{err}</p>}
      {(out || busy) && <div className="mt-3 whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm">{out || "Working…"}</div>}
      {tools.length > 0 && <p className="mt-1 text-xs text-slate-500">Used: {[...new Set(tools)].join(", ")}{sid && <> · <Link href={`/copilot?session=${sid}`} className="underline">Open as a session</Link></>}</p>}
    </Card>
  );
}

export default function AssetDetailPage({ kind, keyName }: { kind: Kind; keyName: string }) {
  const me = getClaims();
  const canAuthor = (me?.role === "admin" || me?.role === "editor") && me.companies === null;
  const { data: a, error, loading, reload } = useApi<Detail>(`/${kind}s/${keyName}`);
  const [def, setDef] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null);
  const run = async (fn: () => Promise<string | { text: string; href?: string } | void>) => {
    setMsg(null);
    try { const r = await fn(); if (r) setMsg({ ok: true, ...(typeof r === "string" ? { text: r } : r) }); reload(); }
    catch (e) { setMsg({ ok: false, text: e instanceof SyntaxError ? "The definition is not valid JSON." : e instanceof Error ? e.message : "Failed" }); }
  };
  const propose = (version?: number) => run(async () => {
    const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", { method: "POST", body: JSON.stringify({ action: "publish_asset", args: { asset_id: a!.id, ...(version ? { version } : {}) } }) });
    if (r.verdict === "deny") throw new Error(r.reason);
    return { text: "Sent for approval by a second admin.", href: `/approvals?id=${r.approval.id}` };
  });
  const editing = def ?? (a?.definition ? JSON.stringify(a.definition, null, 2) : "");

  return (
    <div className="max-w-4xl space-y-6">
      <Link href={`/${kind}s`} className="text-sm text-slate-500 hover:underline">← {kind === "skill" ? "Skills" : "Agents"}</Link>
      <Loading error={error} loading={loading && !a} />
      {a && (<>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h1 className="text-2xl font-semibold">{a.name}</h1><p className="mt-1 text-sm text-slate-600">{a.description}</p></div>
          <div className="flex items-center gap-2"><Life v={a.lifecycle} /><PinButton kind={kind} target={a.key} label={a.name} /></div>
        </div>
        <p className="text-xs text-slate-500">{a.builtin ? "Built in (read-only) · " : ""}v{a.version}{a.published_version ? ` · v${a.published_version} is live` : " · not published"} · tools: {a.tools.join(", ") || "none"}{a.model ? ` · model: ${a.model}` : ""}</p>

        {kind === "skill" && (a.published_version !== null || me?.role === "admin") && <RunForm asset={a} kind={kind} />}
        {kind === "agent" && a.published_version !== null && <Link href={`/copilot?agent=${a.key}`} className="inline-block rounded bg-slate-900 px-3 py-1.5 text-sm text-white">Chat with this agent</Link>}

        {canAuthor && a.definition && (
          <Card title="Definition">
            {msg && <p role={msg.ok ? "status" : "alert"} className={`mb-2 text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>{msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}</p>}
            <textarea aria-label="Definition" rows={14} value={editing} readOnly={a.builtin} onChange={(e) => setDef(e.target.value)} className={`${input} font-mono text-xs`} />
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {!a.builtin && <button className="rounded border border-slate-300 px-3 py-1.5" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/versions`, { method: "POST", body: JSON.stringify({ definition: JSON.parse(editing) }) }); setDef(null); return "Saved as a new version. Validate it next."; })}>Save as new version</button>}
              <button className="rounded border border-slate-300 px-3 py-1.5" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/validate`, { method: "POST" }); })}>Validate</button>
              <button className="rounded border border-slate-300 px-3 py-1.5" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/evals`, { method: "POST" }); return "Evals finished."; })}>Run evals</button>
              <button className="rounded bg-slate-900 px-3 py-1.5 text-white" onClick={() => propose()}>Propose publishing v{a.version}</button>
              {me?.role === "admin" && !a.builtin && <button className="rounded border border-red-300 px-3 py-1.5 text-red-800" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/deprecate`, { method: "POST" }); })}>Deprecate</button>}
            </div>
            {a.validation && (
              <div className="mt-4"><h3 className="mb-1 text-xs uppercase text-slate-500">Last validation {a.validation.ok ? "· passed" : "· failed"}</h3>
                <ul className="space-y-0.5 text-xs">{a.validation.checks.map((c) => <li key={c.name} className={c.ok ? "text-emerald-800" : "text-red-700"}>{c.ok ? "✓" : "✗"} {c.name.replace(/_/g, " ")}{c.detail ? `: ${c.detail}` : ""}</li>)}</ul></div>)}
            <div className="mt-4"><h3 className="mb-1 text-xs uppercase text-slate-500">Versions</h3>
              <ul className="space-y-1 text-xs">{a.versions?.map((v) => (
                <li key={v.version}><div className="flex items-center justify-between"><span>v{v.version} · {v.validated ? "validated" : "not validated"} · evals {v.eval_passed === null ? "not run" : v.eval_passed ? "passed" : "failed"}{v.published ? " · LIVE" : ""}</span>
                  {v.validated && !v.published && <button className="underline" onClick={() => propose(v.version)}>Propose this version</button>}</div>
                  {v.eval_results?.cases.filter((c) => !c.passed).map((c) => <div key={c.case} className="ml-3 text-red-700">✗ {c.case}: {c.problems.join("; ")}</div>)}</li>))}</ul></div>
          </Card>)}
      </>)}
    </div>
  );
}
