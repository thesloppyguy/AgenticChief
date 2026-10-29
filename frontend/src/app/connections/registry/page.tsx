"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, Loading } from "@/components/ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Approval, CapabilityDetail, CapabilityRow, ConnectionRow, DiscoverSummary, MappingRow } from "@/lib/types";

const OK = "border-success/30 bg-success/10 text-success";
const WARN = "border-warning/30 bg-warning/10 text-warning";
const BAD = "border-destructive/30 bg-destructive/10 text-destructive";
const RISK: Record<string, string> = {
  read: OK, internal_write: WARN, external_message: WARN, destructive: BAD,
};
const LIFE: Record<string, string> = {
  published: OK, validated: "bg-secondary text-secondary-foreground",
  draft: "bg-muted text-muted-foreground", update_pending: WARN,
  deprecated: "bg-muted text-muted-foreground opacity-70", removed: BAD,
};
const Pill = ({ text, cls }: { text: string; cls?: string }) => (
  <Badge variant="outline" className={cls}>{label(text)}</Badge>
);
const ALL = "all";  // Select values cannot be empty; maps to "no filter"
const TYPE_ITEMS = [
  { value: "mcp", label: "MCP server" }, { value: "api", label: "REST API (OpenAPI)" }, { value: "function", label: "Function tools (built in)" },
];
const RISK_ITEMS = ["read", "internal_write", "external_message", "destructive"].map((r) => ({ value: r, label: label(r) }));
const LIFE_ITEMS = [{ value: ALL, label: "All" }, ...Object.keys(LIFE).map((l) => ({ value: l, label: label(l) }))];

function ResultAlert({ msg, className }: { msg: { ok: boolean; text: string; href?: string }; className?: string }) {
  return (
    <Alert role={msg.ok ? "status" : "alert"} variant={msg.ok ? "default" : "destructive"} className={cn(msg.ok && "text-success", className)}>
      <AlertDescription className={cn(msg.ok && "text-success")}>
        {msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}
      </AlertDescription>
    </Alert>
  );
}

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
          <div className="space-y-1"><Label htmlFor="conn-name">Name</Label><Input id="conn-name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="space-y-1"><Label htmlFor="conn-type">Type</Label>
            <Select items={TYPE_ITEMS} value={type} onValueChange={(v) => v != null && setType(v as typeof type)}>
              <SelectTrigger id="conn-type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{TYPE_ITEMS.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
            </Select></div>
        </div>
        {type === "mcp" && <div className="space-y-1"><Label htmlFor="conn-url">Server URL (Streamable HTTP)</Label><Input id="conn-url" required value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://hr-mcp.internal/mcp" /></div>}
        {type === "api" && (<>
          <div className="space-y-1"><Label htmlFor="conn-spec">OpenAPI document (paste JSON or YAML)</Label><Textarea id="conn-spec" required rows={4} value={f.spec} onChange={(e) => setF({ ...f, spec: e.target.value })} className="font-mono text-xs" /></div>
          <div className="space-y-1"><Label htmlFor="conn-server">Server URL (optional, overrides the document)</Label><Input id="conn-server" value={f.server_url} onChange={(e) => setF({ ...f, server_url: e.target.value })} /></div></>)}
        {type !== "function" && (
          <div className="space-y-1"><Label htmlFor="conn-token">Token: name of the environment variable that holds it (optional)</Label>
            <Input id="conn-token" value={f.token_env} onChange={(e) => setF({ ...f, token_env: e.target.value.toUpperCase() })} placeholder="HR_MCP_TOKEN" /></div>)}
        <p className="text-xs text-muted-foreground">Secrets are never entered here or stored: set the variable on the server and give only its name.</p>
        {msg && <Alert role="status"><AlertDescription>{msg}</AlertDescription></Alert>}
        <Button type="submit">Add</Button>
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
          <p>{c.description || <em className="text-muted-foreground">No description.</em>}</p>
          <div className="flex flex-wrap gap-2"><Pill text={c.risk} cls={RISK[c.risk]} /><Pill text={c.lifecycle} cls={LIFE[c.lifecycle]} />
            {c.risk_overridden && <Pill text="risk reclassified" />}</div>
          <p className="text-xs text-muted-foreground">Latest v{c.version} · validated {c.validated_version ? `v${c.validated_version}` : "never"} · published {c.published_version ? `v${c.published_version}` : "no"}
            {c.kpis_using_it.length > 0 && <> · feeds {c.kpis_using_it.map(label).join(", ")}</>}</p>

          <div className="space-y-2">
            <Separator />
            <div className="space-y-1 pt-1"><Label htmlFor="sample">Sample arguments (JSON)</Label><Textarea id="sample" rows={2} value={sample} onChange={(e) => setSample(e.target.value)} className="font-mono text-xs" /></div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => run(async () => { await api(`/capabilities/${id}/validate`, { method: "POST", body: JSON.stringify({ sample_args: json() }) }); done(); })}>Validate</Button>
              <Button variant="outline" disabled={c.risk !== "read"} title={c.risk !== "read" ? "Only read capabilities can be test-called" : ""}
                onClick={() => run(async () => { const r = await api<unknown>(`/capabilities/${id}/test`, { method: "POST", body: JSON.stringify({ args: json() }) }); setOut(JSON.stringify(r, null, 2)); })}>Test call</Button>
              <Button onClick={() => run(() => proposePublish())}>Propose publishing v{c.version}</Button>
              <Button variant="destructive" onClick={() => run(async () => { await api(`/capabilities/${id}/deprecate`, { method: "POST" }); done(); })}>Deprecate</Button>
            </div>
            {msg && <ResultAlert msg={msg} />}
            {out && <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs">{out}</pre>}
          </div>

          {c.validation && (
            <div><h3 className="mb-1 text-xs uppercase text-muted-foreground">Last validation {c.validation.ok ? "· passed" : "· failed"}</h3>
              <ul className="space-y-0.5 text-xs">{c.validation.checks.map((k) => (
                <li key={k.name} className={k.ok ? "text-success" : "text-destructive"}>{k.ok ? "✓" : "✗"} {label(k.name)}{k.skipped ? " (skipped)" : ""}{k.detail ? `: ${k.detail}` : ""}</li>))}</ul></div>
          )}

          <div><h3 className="mb-1 text-xs uppercase text-muted-foreground">Versions (roll back by publishing an older validated one)</h3>
            <ul className="space-y-1 text-xs">{c.versions.map((v) => (
              <li key={v.version} className="flex items-center justify-between"><span>v{v.version} · {label(v.risk)} · {v.validated ? "validated" : "not validated"}{v.published ? " · LIVE" : ""}</span>
                {v.validated && !v.published && <Button variant="link" size="xs" onClick={() => run(() => proposePublish(v.version))}>Propose this version</Button>}</li>))}</ul></div>

          <div>
            <Separator className="mb-3" />
            <h3 className="mb-1 text-xs uppercase text-muted-foreground">Who may use it in the Copilot</h3>
            {c.risk !== "read" || c.published_version === null ? (
              <p className="text-xs text-muted-foreground">Only published, read-only capabilities can be offered to the Copilot.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <Label className="gap-1 text-muted-foreground"><Checkbox checked disabled /> admin (always)</Label>
                {(["editor", "viewer"] as const).map((role) => (
                  <Label key={role} className="gap-1"><Checkbox checked={c.permissions?.includes(role) ?? false}
                    onCheckedChange={(checked) => run(async () => { await api(`/capabilities/${id}/permissions`, { method: "POST", body: JSON.stringify({ roles: checked ? [...(c.permissions ?? []).filter((r) => r !== role), role] : (c.permissions ?? []).filter((r) => r !== role) }) }); done(); })} /> {role}</Label>))}
              </div>)}
            <p className="mt-1 text-xs text-muted-foreground">Group-wide users only, never users limited to some companies: an external system&apos;s data is not filtered by company. The Copilot treats the result as data.</p>
          </div>

          <Separator />
          <details><summary className="cursor-pointer text-muted-foreground">Reclassify risk</summary>
            <div className="mt-2 space-y-2">
              <Select items={RISK_ITEMS} value={risk.risk} onValueChange={(v) => v != null && setRisk({ ...risk, risk: v })}>
                <SelectTrigger aria-label="Risk class" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{RISK_ITEMS.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
              </Select>
              <Input aria-label="Reason" placeholder="Reason (required)" value={risk.reason} onChange={(e) => setRisk({ ...risk, reason: e.target.value })} />
              <Button variant="outline" onClick={() => run(async () => { await api(`/capabilities/${id}/risk`, { method: "POST", body: JSON.stringify(risk) }); done(); })}>Apply as a new version</Button>
              <p className="text-xs text-muted-foreground">A reclassified tool is a new version: it must be validated and published again, with a second admin&apos;s approval.</p>
            </div></details>

          <details><summary className="cursor-pointer text-muted-foreground">Schemas</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs">{JSON.stringify({ input: c.input_schema, output: c.output_schema }, null, 2)}</pre></details>
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
    <Card title="KPI mappings" action={<Button variant="outline" size="sm" onClick={() => run(async () => { const r = await api<{ recommended: number }>("/kpi-mappings/recommend", { method: "POST" }); return `${r.recommended} recommendation(s).`; })}>Recommend mappings</Button>}>
      <p className="mb-3 text-sm text-muted-foreground">An approved mapping makes the platform pull that KPI&apos;s raw counts through the capability. Only published <strong>read</strong> capabilities can be approved, and a second admin must approve.</p>
      {msg && <ResultAlert msg={msg} className="mb-2" />}
      <Loading error={maps.error} loading={maps.loading && !maps.data} />
      <ul className="divide-y text-sm">
        {maps.data?.map((m) => (
          <li key={m.id} className="space-y-1 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><strong>{label(m.kpi_key)}</strong> ← {m.capability_key} <span className="text-xs text-muted-foreground">· score {m.score}</span></span>
              <span className="flex items-center gap-3"><Pill text={m.status} />
                {m.status === "recommended" && (<>
                  <Button variant="link" size="xs" onClick={() => setEditing({ id: m.id, field_map: JSON.stringify(m.field_map, null, 1), arg_template: JSON.stringify(m.arg_template, null, 1) })}>Edit</Button>
                  <Button variant="link" size="xs" onClick={() => run(async () => { const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", { method: "POST", body: JSON.stringify({ action: "approve_kpi_mapping", args: { mapping_id: m.id } }) }); if (r.verdict === "deny") throw new Error(r.reason); return { text: "Sent for approval.", href: `/approvals?id=${r.approval.id}` }; })}>Propose approval</Button></>)}
                {(m.status === "recommended" || m.status === "approved") && (
                  <Button variant="link" size="xs" className="text-destructive" onClick={() => { const reason = window.prompt("Reason for rejecting this mapping?"); if (reason) run(async () => { await api(`/kpi-mappings/${m.id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }); }); }}>Reject</Button>)}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">{Object.entries(m.field_map).map(([k, v]) => `${k} ← ${v}`).join(" · ") || "no field mapping yet"}{m.reasons?.length ? ` — ${m.reasons.join("; ")}` : ""}</div>
            {editing?.id === m.id && (
              <div className="space-y-2 rounded-md bg-muted p-2">
                <div className="space-y-1"><Label className="text-xs" htmlFor={`fm-${m.id}`}>Field map (KPI raw field → path in the output)</Label><Textarea id={`fm-${m.id}`} rows={3} value={editing.field_map} onChange={(e) => setEditing({ ...editing, field_map: e.target.value })} className="font-mono text-xs" /></div>
                <div className="space-y-1"><Label className="text-xs" htmlFor={`at-${m.id}`}>Arguments (use {"{company_code}"}, {"{period}"}, {"{year}"}, {"{month}"})</Label><Textarea id={`at-${m.id}`} rows={3} value={editing.arg_template} onChange={(e) => setEditing({ ...editing, arg_template: e.target.value })} className="font-mono text-xs" /></div>
                <Button size="sm" onClick={() => run(async () => { await api(`/kpi-mappings/${m.id}`, { method: "PATCH", body: JSON.stringify({ field_map: JSON.parse(editing.field_map), arg_template: JSON.parse(editing.arg_template) }) }); setEditing(null); return "Saved."; })}>Save</Button>
              </div>)}
          </li>
        ))}
        {maps.data?.length === 0 && <li className="py-2 text-muted-foreground">No mappings yet. Discover capabilities, then recommend.</li>}
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
      <Link href="/connections" className="text-sm text-muted-foreground hover:underline">← Connections</Link>
      <h1 className="text-2xl font-semibold">Capability registry</h1>
      <p className="text-sm text-muted-foreground">Configure a connection once. Its tools are discovered, reviewed, validated and published here, then reused for KPI data. Discovering a tool never authorizes it.</p>
      {msg && <Alert role="status"><AlertDescription>{msg}</AlertDescription></Alert>}

      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-6">
          <Card title="Connections">
            <Loading error={conns.error} loading={conns.loading && !conns.data} />
            <ul className="divide-y text-sm">
              {conns.data?.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 py-2">
                  <span><strong>{c.name}</strong> <span className="text-xs text-muted-foreground">{c.type} · {c.capability_count} tools · {c.health_status}{c.health_detail ? ` (${c.health_detail})` : ""}</span></span>
                  <span className="flex gap-1"><Button variant="outline" size="xs" onClick={() => act(c.id, "health")}>Health</Button><Button variant="outline" size="xs" onClick={() => act(c.id, "discover")}>Discover</Button></span>
                </li>))}
              {conns.data?.length === 0 && <li className="py-2 text-muted-foreground">None yet.</li>}
            </ul>
          </Card>
          <AddConnection onDone={conns.reload} />
        </div>

        <Card title="Capabilities"
          action={<div className="flex gap-2 text-sm">
            <Input aria-label="Search capabilities" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} className="w-auto" />
            <Select items={LIFE_ITEMS} value={lifecycle || ALL} onValueChange={(v) => v != null && setLifecycle(v === ALL ? "" : v)}>
              <SelectTrigger aria-label="Filter by lifecycle"><SelectValue /></SelectTrigger>
              <SelectContent>{LIFE_ITEMS.map((l) => <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>)}</SelectContent>
            </Select></div>}>
          <Loading error={caps.error} loading={caps.loading && !caps.data} />
          <ul className="divide-y text-sm">
            {caps.data?.map((c) => (
              <li key={c.id}>
                <Button variant="ghost" onClick={() => setSel(c.id)} className={cn("h-auto w-full justify-between gap-2 py-2 text-left font-normal", c.id === sel && "bg-muted")}>
                  <span className="truncate">{c.key}</span><span className="flex shrink-0 gap-1"><Pill text={c.risk} cls={RISK[c.risk]} /><Pill text={c.lifecycle} cls={LIFE[c.lifecycle]} /></span>
                </Button>
              </li>))}
            {caps.data?.length === 0 && <li className="py-2 text-muted-foreground">No capabilities. Add a connection and run Discover.</li>}
          </ul>
        </Card>
      </div>

      {sel && <CapabilityPanel key={sel} id={sel} onChange={caps.reload} />}
      <Mappings />
    </div>
  );
}
