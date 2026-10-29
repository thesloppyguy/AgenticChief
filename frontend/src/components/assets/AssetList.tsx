"use client";
import { useState } from "react";
import Link from "next/link";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, Loading } from "@/components/ui";
import { api, getClaims } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { type AssetSummary, type Kind, TEMPLATES } from "./types";

const LIFE: Record<string, string> = {
  published: "border-success/30 bg-success/10 text-success", validated: "border-primary/30 bg-primary/10 text-primary",
  draft: "text-muted-foreground", update_pending: "border-warning/30 bg-warning/10 text-warning", deprecated: "bg-muted text-muted-foreground",
};
export const Life = ({ v }: { v: string }) => <Badge variant="outline" className={LIFE[v] ?? ""}>{v.replace("_", " ")}</Badge>;

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
  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">{plural}</h1>
      <p className="text-sm text-muted-foreground">
        {kind === "skill" ? "A skill is a reusable task: typed inputs, the tools it may use, and instructions. Run one with a few clicks."
          : "An agent is a specialist: its own instructions, tools and model. Pick one in Ask Copilot."}{" "}
        New ones start as drafts, are validated, and go live only after a second admin approves.
      </p>
      <Loading error={error} loading={loading && !data} />
      <ul className="grid gap-3 md:grid-cols-2">
        {data?.map((a) => (
          <li key={a.key} className="rounded-lg border bg-card p-4">
            <div className="flex items-start justify-between gap-2"><Link href={`/${kind}s/${a.key}`} className="font-medium hover:underline">{a.name}</Link><Life v={a.lifecycle} /></div>
            <p className="mt-1 text-sm text-muted-foreground">{a.description}</p>
            <p className="mt-2 text-xs text-muted-foreground">{a.builtin ? "Built in · " : ""}tools: {a.tools.join(", ") || "none"}</p>
          </li>))}
        {data?.length === 0 && <li className="text-sm text-muted-foreground">None yet.</li>}
      </ul>
      {canAuthor && (
        <Card title={`New ${kind}`}>
          <form onSubmit={create} className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col items-start gap-1.5"><Label htmlFor="asset-key">Key (letters, digits, underscores)</Label><Input id="asset-key" required value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} /></div>
              <div className="flex flex-col items-start gap-1.5"><Label htmlFor="asset-name">Name</Label><Input id="asset-name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
            </div>
            <div className="flex flex-col items-start gap-1.5"><Label htmlFor="asset-desc">Description</Label><Input id="asset-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
            <div className="flex flex-col items-start gap-1.5"><Label htmlFor="asset-def">Definition (JSON)</Label><Textarea id="asset-def" rows={12} value={f.definition} onChange={(e) => setF({ ...f, definition: e.target.value })} className="font-mono text-xs" /></div>
            {msg && <Alert role="status"><AlertDescription>{msg}</AlertDescription></Alert>}
            <Button type="submit">Create draft</Button>
          </form>
        </Card>)}
    </div>
  );
}
