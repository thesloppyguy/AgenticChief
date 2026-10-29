"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Approval, CapabilityDetail, CapabilityRow, ConnectionRow, DiscoverSummary, MappingRow } from "@/lib/types";

const RISK: Record<string, string> = {
  read: "bg-emerald-50 text-emerald-800 ring-emerald-200", internal_write: "bg-amber-50 text-amber-800 ring-amber-200",
  external_message: "bg-amber-50 text-amber-800 ring-amber-200", destructive: "bg-red-50 text-red-800 ring-red-200",
};
const LIFE: Record<string, string> = {
  published: "bg-emerald-50 text-emerald-800 ring-emerald-200", validated: "bg-blue-50 text-blue-800 ring-blue-200",
  draft: "bg-slate-50 text-slate-700 ring-slate-300", update_pending: "bg-amber-50 text-amber-800 ring-amber-200",
  deprecated: "bg-slate-100 text-slate-500 ring-slate-300", removed: "bg-red-50 text-red-800 ring-red-200",
};
const Pill = ({ text, cls }: { text: string; cls?: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${cls ?? "bg-slate-50 ring-slate-200"}`}>{label(text)}</span>
);
const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";

function AddConnection({ onDone }: { onDone: () => void }) {
  const [type, setType] = useState<"mcp" | "api" | "function">("mcp");
  const [f, setF] = useState({ name: "", url: "", spec: "", server_url: "", token_env: "" });
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const auth = f.token_env ? { type: "bearer", token_env: f.token_env } : { type: "none" };
    const config = type === "mcp" ? { url: f.url, auth } : type === "api" ? { spec: f.spec, ...(f.server_url ? { server_url: f.server_url } : {}), auth } : {};
    try { await api("/connections", { method: "POST", body: JSON.stringify({ name: f.name, type, config }) }); setMsg("Added."); onDone(); }
    catch (err) { setMsg(err instanceof Error ? err.message : "Failed"); }
  }
  return (
    <Card title="Add a connection">
      <form onSubmit={submit} className="space-y-2 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <label>Name<input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className={input} /></label>
          <label>Type<select value={type} onChange={(e) => setType(e.target.value as typeof type)} className={input}>
            <option value="mcp">MCP server</option><option value="api">REST API (OpenAPI)</option><option value="function">Function tools (built in)</option></select></label>
        </div>
        {type === "mcp" && <label className="block">Server URL (Streamable HTTP)<input required value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://hr-mcp.internal/mcp" className={input} /></label>}
        {type === "api" && (<>
          <label className="block">OpenAPI document (paste JSON or YAML)<textarea required rows={4} value={f.spec} onChange={(e) => setF({ ...f, spec: e.target.value })} className={`${input} font-mono text-xs`} /></label>
          <label className="block">Server URL (optional, overrides the document)<input value={f.server_url} onChange={(e) => setF({ ...f, server_url: e.target.value })} className={input} /></label></>)}
        {type !== "function" && (
          <label className="block">Token: name of the environment variable that holds it (optional)
            <input value={f.token_env} onChange={(e) => setF({ ...f, token_env: e.target.value.toUpperCase() })} placeholder="HR_MCP_TOKEN" className={input} /></label>)}
        <p className="text-xs text-slate-500">Secrets are never entered here or stored: set the variable on the server and give only its name.</p>
        {msg && <p role="status" className="text-slate-700">{msg}</p>}
        <button className="rounded bg-slate-900 px-3 py-1.5 text-white">Add</button>
      </form>
    </Card>
  );
}

function CapabilityPanel({ id, onChange }: { id: number; onChange: () => void }) {
  const { data: c, error, loading, reload } = useApi<CapabilityDetail>(`/capabilities/${id}`);
  const [sample, setSample] = useState("{}");
  const [out, setOut] = useState<string | null>(null);
  const [risk, setRisk] = useState({ risk: "read", reason: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null);
  const done = () => { reload(); onChange(); };
  const run = async (fn: () => Promise<unknown>) => { setMsg(null); try { await fn(); } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" }); } };
  const json = () => { try { return JSON.parse(sample || "{}"); } catch { throw new Error("Sample arguments are not valid JSON"); } };

  async function proposePublish(version?: number) {
    const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", { method: "POST", body: JSON.stringify({ action: "publish_capability", args: { capability_id: id, ...(version ? { version } : {}) } }) });
    setMsg(r.verdict === "deny" ? { ok: false, text: r.reason } : { ok: true, text: "Sent for approval by a second admin.", href: `/approvals?id=${r.approval.id}` });
  }

  return (
    <Card title={c?.key ?? "Capability"}>
      <Loading error={error} loading={loading && !c} />
      {c && (
        <div className="space-y-4 text-sm">
          <p>{c.description || <em className="text-slate-500">No description.</em>}</p>
          <div className="flex flex-wrap gap-2"><Pill text={c.risk} cls={RISK[c.risk]} /><Pill text={c.lifecycle} cls={LIFE[c.lifecycle]} />
            {c.risk_overridden && <Pill text="risk reclassified" />}</div>
          <p className="text-xs text-slate-600">Latest v{c.version} · validated {c.validated_version ? `v${c.validated_version}` : "never"} · published {c.published_version ? `v${c.published_version}` : "no"}
            {c.kpis_using_it.length > 0 && <> · feeds {c.kpis_using_it.map(label).join(", ")}</>}</p>

          <div className="space-y-2 border-t border-slate-100 pt-3">
            <label className="block">Sample arguments (JSON)<textarea rows={2} value={sample} onChange={(e) => setSample(e.target.value)} className={`${input} font-mono text-xs`} /></label>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => run(async () => { await api(`/capabilities/${id}/validate`, { method: "POST", body: JSON.stringify({ sample_args: json() }) }); done(); })} className="rounded border border-slate-300 px-3 py-1.5">Validate</button>
              <button disabled={c.risk !== "read"} title={c.risk !== "read" ? "Only read capabilities can be test-called" : ""}
                onClick={() => run(async () => { const r = await api<unknown>(`/capabilities/${id}/test`, { method: "POST", body: JSON.stringify({ args: json() }) }); setOut(JSON.stringify(r, null, 2)); })}
                className="rounded border border-slate-300 px-3 py-1.5 disabled:opacity-40">Test call</button>
              <button onClick={() => run(() => proposePublish())} className="rounded bg-slate-900 px-3 py-1.5 text-white">Propose publishing v{c.version}</button>
              <button onClick={() => run(async () => { await api(`/capabilities/${id}/deprecate`, { method: "POST" }); done(); })} className="rounded border border-red-300 px-3 py-1.5 text-red-800">Deprecate</button>
            </div>
            {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-emerald-700" : "text-red-700"}>{msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}</p>}
            {out && <pre className="max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs">{out}</pre>}
          </div>

          {c.validation && (
            <div><h3 className="mb-1 text-xs uppercase text-slate-500">Last validation {c.validation.ok ? "· passed" : "· failed"}</h3>
              <ul className="space-y-0.5 text-xs">{c.validation.checks.map((k) => (
                <li key={k.name} className={k.ok ? "text-emerald-800" : "text-red-700"}>{k.ok ? "✓" : "✗"} {label(k.name)}{k.skipped ? " (skipped)" : ""}{k.detail ? `: ${k.detail}` : ""}</li>))}</ul></div>
          )}

          <div><h3 className="mb-1 text-xs uppercase text-slate-500">Versions (roll back by publishing an older validated one)</h3>
            <ul className="space-y-1 text-xs">{c.versions.map((v) => (
              <li key={v.version} className="flex items-center justify-between"><span>v{v.version} · {label(v.risk)} · {v.validated ? "validated" : "not validated"}{v.published ? " · LIVE" : ""}</span>
                {v.validated && !v.published && <button onClick={() => run(() => proposePublish(v.version))} className="underline">Propose this version</button>}</li>))}</ul></div>

          <div className="border-t border-slate-100 pt-3">
            <h3 className="mb-1 text-xs uppercase text-slate-500">Who may use it in the Copilot</h3>
            {c.risk !== "read" || c.published_version === null ? (
              <p className="text-xs text-slate-500">Only published, read-only capabilities can be offered to the Copilot.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <label className="flex items-center gap-1 text-slate-500"><input type="checkbox" checked disabled /> admin (always)</label>
                {(["editor", "viewer"] as const).map((role) => (
                  <label key={role} className="flex items-center gap-1"><input type="checkbox" checked={c.permissions?.includes(role) ?? false}
                    onChange={(e) => run(async () => { await api(`/capabilities/${id}/permissions`, { method: "POST", body: JSON.stringify({ roles: e.target.checked ? [...(c.permissions ?? []).filter((r) => r !== role), role] : (c.permissions ?? []).filter((r) => r !== role) }) }); done(); })} /> {role}</label>))}
              </div>)}
            <p className="mt-1 text-xs text-slate-500">Group-wide users only, never users limited to some companies: an external system&apos;s data is not filtered by company. The Copilot treats the result as data.</p>
          </div>

          <details className="border-t border-slate-100 pt-3"><summary className="cursor-pointer text-slate-600">Reclassify risk</summary>
            <div className="mt-2 space-y-2">
              <select value={risk.risk} onChange={(e) => setRisk({ ...risk, risk: e.target.value })} className={input}>
                {["read", "internal_write", "external_message", "destructive"].map((r) => <option key={r} value={r}>{label(r)}</option>)}</select>
              <input placeholder="Reason (required)" value={risk.reason} onChange={(e) => setRisk({ ...risk, reason: e.target.value })} className={input} />
              <button onClick={() => run(async () => { await api(`/capabilities/${id}/risk`, { method: "POST", body: JSON.stringify(risk) }); done(); })} className="rounded border border-slate-300 px-3 py-1.5">Apply as a new version</button>
              <p className="text-xs text-slate-500">A reclassified tool is a new version: it must be validated and published again, with a second admin&apos;s approval.</p>
            </div></details>

          <details><summary className="cursor-pointer text-slate-600">Schemas</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify({ input: c.input_schema, output: c.output_schema }, null, 2)}</pre></details>
        </div>
      )}
    </Card>
  );
}

function Mappings() {
  const maps = useApi<MappingRow[]>("/kpi-mappings");
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null);
  const [editing, setEditing] = useState<{ id: number; field_map: string; arg_template: string } | null>(null);
  const run = async (fn: () => Promise<string | { text: string; href?: string } | void>) => {
    setMsg(null);
    try { const r = await fn(); if (r) setMsg({ ok: true, ...(typeof r === "string" ? { text: r } : r) }); maps.reload(); }
    catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" }); }
  };
  return (
    <Card title="KPI mappings" action={<button onClick={() => run(async () => { const r = await api<{ recommended: number }>("/kpi-mappings/recommend", { method: "POST" }); return `${r.recommended} recommendation(s).`; })} className="text-sm underline">Recommend mappings</button>}>
      <p className="mb-3 text-sm text-slate-600">An approved mapping makes the platform pull that KPI&apos;s raw counts through the capability. Only published <strong>read</strong> capabilities can be approved, and a second admin must approve.</p>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`mb-2 text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>{msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}</p>}
      <Loading error={maps.error} loading={maps.loading && !maps.data} />
      <ul className="divide-y divide-slate-100 text-sm">
        {maps.data?.map((m) => (
          <li key={m.id} className="space-y-1 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><strong>{label(m.kpi_key)}</strong> ← {m.capability_key} <span className="text-xs text-slate-500">· score {m.score}</span></span>
              <span className="flex items-center gap-3"><Pill text={m.status} />
                {m.status === "recommended" && (<>
                  <button className="underline" onClick={() => setEditing({ id: m.id, field_map: JSON.stringify(m.field_map, null, 1), arg_template: JSON.stringify(m.arg_template, null, 1) })}>Edit</button>
                  <button className="underline" onClick={() => run(async () => { const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", { method: "POST", body: JSON.stringify({ action: "approve_kpi_mapping", args: { mapping_id: m.id } }) }); if (r.verdict === "deny") throw new Error(r.reason); return { text: "Sent for approval.", href: `/approvals?id=${r.approval.id}` }; })}>Propose approval</button></>)}
                {(m.status === "recommended" || m.status === "approved") && (
                  <button className="underline text-red-800" onClick={() => { const reason = window.prompt("Reason for rejecting this mapping?"); if (reason) run(async () => { await api(`/kpi-mappings/${m.id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }); }); }}>Reject</button>)}
              </span>
            </div>
            <div className="text-xs text-slate-600">{Object.entries(m.field_map).map(([k, v]) => `${k} ← ${v}`).join(" · ") || "no field mapping yet"}{m.reasons?.length ? ` — ${m.reasons.join("; ")}` : ""}</div>
            {editing?.id === m.id && (
              <div className="space-y-2 rounded bg-slate-50 p-2">
                <label className="block text-xs">Field map (KPI raw field → path in the output)<textarea rows={3} value={editing.field_map} onChange={(e) => setEditing({ ...editing, field_map: e.target.value })} className={`${input} font-mono text-xs`} /></label>
                <label className="block text-xs">Arguments (use {"{company_code}"}, {"{period}"}, {"{year}"}, {"{month}"})<textarea rows={3} value={editing.arg_template} onChange={(e) => setEditing({ ...editing, arg_template: e.target.value })} className={`${input} font-mono text-xs`} /></label>
                <button className="rounded bg-slate-900 px-3 py-1 text-xs text-white" onClick={() => run(async () => { await api(`/kpi-mappings/${m.id}`, { method: "PATCH", body: JSON.stringify({ field_map: JSON.parse(editing.field_map), arg_template: JSON.parse(editing.arg_template) }) }); setEditing(null); return "Saved."; })}>Save</button>
              </div>)}
          </li>
        ))}
        {maps.data?.length === 0 && <li className="py-2 text-slate-500">No mappings yet. Discover capabilities, then recommend.</li>}
      </ul>
    </Card>
  );
}

export default function Registry() {
  const conns = useApi<ConnectionRow[]>("/connections");
  const [q, setQ] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const params = new URLSearchParams({ ...(q ? { q } : {}), ...(lifecycle ? { lifecycle } : {}) }).toString();
  const caps = useApi<CapabilityRow[]>(`/capabilities${params ? `?${params}` : ""}`);
  const [sel, setSel] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function act(id: number, what: "discover" | "health") {
    setMsg(null);
    try {
      const r = await api<DiscoverSummary & { healthy?: boolean; detail?: string }>(`/connections/${id}/${what}`, { method: "POST" });
      setMsg(what === "health" ? `Health: ${r.healthy ? "healthy" : "unhealthy"} (${r.detail})`
        : `Discovered: ${r.added.length} new, ${r.changed.length} changed, ${r.removed.length} removed.${r.impacts.length ? ` ⚠ ${r.impacts.map((i) => `${i.capability}${i.kpis.length ? ` (affects ${i.kpis.join(", ")})` : ""}`).join("; ")}` : ""}`);
      conns.reload(); caps.reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <div className="max-w-6xl space-y-6">
      <Link href="/connections" className="text-sm text-slate-500 hover:underline">← Connections</Link>
      <h1 className="text-2xl font-semibold">Capability registry</h1>
      <p className="text-sm text-slate-600">Configure a connection once. Its tools are discovered, reviewed, validated and published here, then reused for KPI data. Discovering a tool never authorizes it.</p>
      {msg && <p role="status" className="rounded bg-slate-100 p-2 text-sm">{msg}</p>}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-6">
          <Card title="Connections">
            <Loading error={conns.error} loading={conns.loading && !conns.data} />
            <ul className="divide-y divide-slate-100 text-sm">
              {conns.data?.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 py-2">
                  <span><strong>{c.name}</strong> <span className="text-xs text-slate-500">{c.type} · {c.capability_count} tools · {c.health_status}{c.health_detail ? ` (${c.health_detail})` : ""}</span></span>
                  <span className="flex gap-3 text-xs"><button className="underline" onClick={() => act(c.id, "health")}>Health</button><button className="underline" onClick={() => act(c.id, "discover")}>Discover</button></span>
                </li>))}
              {conns.data?.length === 0 && <li className="py-2 text-slate-500">None yet.</li>}
            </ul>
          </Card>
          <AddConnection onDone={conns.reload} />
        </div>

        <Card title="Capabilities"
          action={<div className="flex gap-2 text-sm">
            <input aria-label="Search capabilities" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} className="rounded border border-slate-300 px-2 py-1" />
            <select aria-label="Filter by lifecycle" value={lifecycle} onChange={(e) => setLifecycle(e.target.value)} className="rounded border border-slate-300 px-2 py-1">
              <option value="">All</option>{Object.keys(LIFE).map((l) => <option key={l} value={l}>{label(l)}</option>)}</select></div>}>
          <Loading error={caps.error} loading={caps.loading && !caps.data} />
          <ul className="divide-y divide-slate-100 text-sm">
            {caps.data?.map((c) => (
              <li key={c.id}>
                <button onClick={() => setSel(c.id)} className={`flex w-full items-center justify-between gap-2 py-2 text-left hover:bg-slate-50 ${c.id === sel ? "bg-slate-50" : ""}`}>
                  <span className="truncate">{c.key}</span><span className="flex shrink-0 gap-1"><Pill text={c.risk} cls={RISK[c.risk]} /><Pill text={c.lifecycle} cls={LIFE[c.lifecycle]} /></span>
                </button>
              </li>))}
            {caps.data?.length === 0 && <li className="py-2 text-slate-500">No capabilities. Add a connection and run Discover.</li>}
          </ul>
        </Card>
      </div>

      {sel && <CapabilityPanel key={sel} id={sel} onChange={caps.reload} />}
      <Mappings />
    </div>
  );
}
