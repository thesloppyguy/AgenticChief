"use client";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Mem { id: number; kind: string; domain: string; summary: string; pinned: boolean; created_at: string; session_id: number | null }
const KIND: Record<string, "default" | "secondary" | "outline"> = { decision: "default", initiative: "secondary", advice: "outline" };

export default function Memories() {
  const { data, error, loading, reload } = useApi<{ enabled: boolean; memories: Mem[] }>("/memories");
  const [err, setErr] = useState<string | null>(null);
  const act = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } };
  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Memories</h1>
      <p className="text-sm text-muted-foreground">
        After a conversation the Copilot may note a decision you made, an initiative you started or advice you accepted, and offer it in later sessions.
        Memories are private to you, fade after 90 days unless pinned, and are context only: the Copilot is told they may be out of date.
        Pure lookups and skill runs are never remembered.
      </p>
      {err && <Alert variant="destructive" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}
      <Loading error={error} loading={loading && !data} />
      {data && (
        <Card title={data.enabled ? "Memory is on" : "Memory is off"}
          action={<Button variant="outline" size="sm" onClick={() => act(() => api("/memories/settings", { method: "PUT", body: JSON.stringify({ enabled: !data.enabled }) }))}>
            {data.enabled ? "Turn off" : "Turn on"}</Button>}>
          <p className="text-sm text-muted-foreground">{data.enabled ? "New conversations can add memories." : "Nothing new is saved or used. Existing memories are kept but not shown to the Copilot."}</p>
        </Card>)}
      <Card title={`Remembered (${data?.memories.length ?? 0})`}
        action={!!data?.memories.length && <Button variant="ghost" size="sm" className="text-destructive" onClick={() => window.confirm("Forget everything the Copilot remembers about you?") && act(() => api("/memories", { method: "DELETE" }))}>Forget everything</Button>}>
        <ul className="divide-y divide-border text-sm">
          {data?.memories.map((m) => (
            <li key={m.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <Badge variant={KIND[m.kind] ?? "outline"} className="mr-2">{m.kind}</Badge>
                {m.pinned && <span className="mr-2 text-xs text-muted-foreground">★ pinned</span>}
                <span>{m.summary}</span>
                <div className="mt-1 text-xs text-muted-foreground">{m.domain} · {new Date(m.created_at).toLocaleDateString()}</div>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button variant="ghost" size="xs" onClick={() => act(() => api(`/memories/${m.id}/pin`, { method: "POST" }))}>{m.pinned ? "Unpin" : "Pin"}</Button>
                <Button variant="ghost" size="xs" className="text-destructive" onClick={() => act(() => api(`/memories/${m.id}`, { method: "DELETE" }))}>Forget</Button>
              </div>
            </li>))}
          {data?.memories.length === 0 && <li className="py-3 text-muted-foreground">Nothing remembered yet.</li>}
        </ul>
      </Card>
    </div>
  );
}
