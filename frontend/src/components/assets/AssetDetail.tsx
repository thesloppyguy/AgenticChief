"use client";
import { useState } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import PinButton from "@/components/PinButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Card, Loading } from "@/components/ui";
import { api, getClaims } from "@/lib/api";
import { streamChat } from "@/lib/chat";
import { useApi } from "@/lib/hooks";
import { Life } from "./AssetList";
import type { Approval } from "@/lib/types";
import type { AssetDetail as Detail, InputSchema, Kind } from "./types";


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
    await streamChat({ skill_name: asset.key, skill_key: asset.key, skill_inputs: inputs, period, allow_draft: draft }, {
      onChunk: (c) => setOut((o) => o + c), onTool: (n) => setTools((t) => [...t, n]),
      onError: setErr, onDone: setSid,
    });
    setBusy(false);
  }
  return (
    <Card title={`Run this ${kind}`}>
      <form onSubmit={run} className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(schema.properties).map(([k, p]) => {
            const id = `run-${k}`;
            const text = <>{k.replace(/_/g, " ")}{schema.required?.includes(k) ? " *" : ""}</>;
            if (p.type === "boolean" && !p.enum) return (
              <div key={k} className="flex items-end gap-2">
                <Checkbox id={id} checked={!!vals[k]} onCheckedChange={(c) => setVals({ ...vals, [k]: c })} /><Label htmlFor={id}>{text}</Label>
              </div>);
            return (
              <div key={k} className="flex flex-col items-start gap-1.5">
                <Label htmlFor={id}>{text}</Label>
                {p.enum ? (
                  <Select items={p.enum.map((o) => ({ value: String(o), label: String(o) }))} value={String(vals[k])} onValueChange={(v) => { if (v != null) setVals({ ...vals, [k]: v }); }}>
                    <SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>{p.enum.map((o) => <SelectItem key={String(o)} value={String(o)}>{String(o)}</SelectItem>)}</SelectContent>
                  </Select>)
                  : k === "period" ? <Input id={id} type="month" required value={String(vals[k])} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />
                  : <Input id={id} type={p.type === "integer" || p.type === "number" ? "number" : "text"} min={p.minimum} max={p.maximum} required={schema.required?.includes(k)} value={String(vals[k])} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />}
              </div>);
          })}
        </div>
        {me?.role === "admin" && asset.published_version === null && <div className="flex items-center gap-2"><Checkbox id="run-draft" checked={draft} onCheckedChange={setDraft} /><Label htmlFor="run-draft">Try the unpublished draft (admin)</Label></div>}
        <Button type="submit" disabled={busy}>{busy ? "Running…" : "Run"}</Button>
      </form>
      {err && <Alert variant="destructive" className="mt-3"><AlertDescription>{err}</AlertDescription></Alert>}
      {(out || busy) && <div className="mt-3 whitespace-pre-wrap rounded bg-muted p-3 text-sm">{out || "Working…"}</div>}
      {tools.length > 0 && <p className="mt-1 text-xs text-muted-foreground">Used: {[...new Set(tools)].join(", ")}{sid && <> · <Link href={`/copilot?session=${sid}`} className="underline">Open as a session</Link></>}</p>}
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
      <Link href={`/${kind}s`} className="text-sm text-muted-foreground hover:underline">← {kind === "skill" ? "Skills" : "Agents"}</Link>
      <Loading error={error} loading={loading && !a} />
      {a && (<>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h1 className="text-2xl font-semibold">{a.name}</h1><p className="mt-1 text-sm text-muted-foreground">{a.description}</p></div>
          <div className="flex items-center gap-2"><Life v={a.lifecycle} /><PinButton kind={kind} target={a.key} label={a.name} /></div>
        </div>
        <p className="text-xs text-muted-foreground">{a.builtin ? "Built in (read-only) · " : ""}v{a.version}{a.published_version ? ` · v${a.published_version} is live` : " · not published"} · tools: {a.tools.join(", ") || "none"}{a.model ? ` · model: ${a.model}` : ""}</p>

        {kind === "skill" && (a.published_version !== null || me?.role === "admin") && <RunForm asset={a} kind={kind} />}
        {kind === "agent" && a.published_version !== null && <Button render={<Link href={`/copilot?agent=${a.key}`} />} nativeButton={false}>Chat with this agent</Button>}

        {canAuthor && a.definition && (
          <Card title="Definition">
            {msg && <Alert role={msg.ok ? "status" : "alert"} variant={msg.ok ? "default" : "destructive"} className={cn("mb-2", msg.ok && "text-success")}><AlertDescription className={msg.ok ? "text-success" : undefined}>{msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}</AlertDescription></Alert>}
            <Textarea aria-label="Definition" rows={14} value={editing} readOnly={a.builtin} onChange={(e) => setDef(e.target.value)} className="font-mono text-xs" />
            <div className="mt-3 flex flex-wrap gap-2">
              {!a.builtin && <Button variant="outline" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/versions`, { method: "POST", body: JSON.stringify({ definition: JSON.parse(editing) }) }); setDef(null); return "Saved as a new version. Validate it next."; })}>Save as new version</Button>}
              <Button variant="outline" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/validate`, { method: "POST" }); })}>Validate</Button>
              <Button variant="outline" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/evals`, { method: "POST" }); return "Evals finished."; })}>Run evals</Button>
              <Button onClick={() => propose()}>Propose publishing v{a.version}</Button>
              {me?.role === "admin" && !a.builtin && <Button variant="destructive" onClick={() => run(async () => { await api(`/${kind}s/${a.key}/deprecate`, { method: "POST" }); })}>Deprecate</Button>}
            </div>
            {a.validation && (
              <div className="mt-4"><h3 className="mb-1 text-xs uppercase text-muted-foreground">Last validation {a.validation.ok ? "· passed" : "· failed"}</h3>
                <ul className="space-y-0.5 text-xs">{a.validation.checks.map((c) => <li key={c.name} className={c.ok ? "text-success" : "text-destructive"}>{c.ok ? "✓" : "✗"} {c.name.replace(/_/g, " ")}{c.detail ? `: ${c.detail}` : ""}</li>)}</ul></div>)}
            <div className="mt-4"><h3 className="mb-1 text-xs uppercase text-muted-foreground">Versions</h3>
              <ul className="space-y-1 text-xs">{a.versions?.map((v) => (
                <li key={v.version}><div className="flex items-center justify-between"><span>v{v.version} · {v.validated ? "validated" : "not validated"} · evals {v.eval_passed === null ? "not run" : v.eval_passed ? "passed" : "failed"}{v.published ? " · LIVE" : ""}</span>
                  {v.validated && !v.published && <Button variant="link" size="xs" onClick={() => propose(v.version)}>Propose this version</Button>}</div>
                  {v.eval_results?.cases.filter((c) => !c.passed).map((c) => <div key={c.case} className="ml-3 text-destructive">✗ {c.case}: {c.problems.join("; ")}</div>)}</li>))}</ul></div>
          </Card>)}
      </>)}
    </div>
  );
}
