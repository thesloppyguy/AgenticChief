"use client";
import { toast } from "sonner";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { label } from "@/lib/format";
import type { MemoryList } from "@/lib/types";

export default function MemoryPage() {
  const { data, error, loading, reload } = useApi<MemoryList>("/memories");

  async function act(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      toast.success(ok);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Memory store</h1>
        <p className="text-sm text-muted-foreground">
          What the Copilot remembers from your earlier sessions. Private to you, and treated as
          possibly out of date: it never quotes a figure from here as current.
        </p>
      </div>

      <Loading error={error} loading={loading && !data} />

      {data && (
        <>
          <Card title="Settings">
            <div className="flex items-start gap-3">
              <Checkbox id="enabled" checked={data.enabled}
                onCheckedChange={(checked) =>
                  act(() => api("/memories/settings", {
                    method: "PUT", body: JSON.stringify({ enabled: Boolean(checked) }),
                  }), Boolean(checked) ? "Memory is on." : "Memory is off.")} />
              <div>
                <label htmlFor="enabled" className="text-sm font-medium">Let the Copilot remember</label>
                <p className="text-xs text-muted-foreground">
                  Memories expire unless you pin them. Turning this off
                  stops new ones being written; it does not delete what is already here.
                </p>
              </div>
            </div>
          </Card>

          <Card title={`Remembered (${data.memories.length})`}
            action={data.memories.length > 0 && (
              <Button variant="ghost" size="sm" className="text-destructive"
                onClick={() => window.confirm("Forget everything?") &&
                  act(() => api("/memories", { method: "DELETE" }), "All forgotten.")}>
                Forget all
              </Button>
            )}>
            {data.memories.length === 0 && (
              <p className="text-sm text-muted-foreground">Nothing remembered yet.</p>
            )}
            <ul className="divide-y">
              {data.memories.map((m) => (
                <li key={m.id} className="flex items-start justify-between gap-3 py-3 text-sm">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{label(m.kind)}</Badge>
                      {m.pinned && <Badge variant="secondary">Pinned</Badge>}
                      <span className="text-xs text-muted-foreground">
                        {new Date(m.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="mt-1">{m.summary}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="sm"
                      onClick={() => act(() => api(`/memories/${m.id}/pin`, { method: "POST" }),
                        m.pinned ? "Unpinned." : "Pinned — it will not expire.")}>
                      {m.pinned ? "Unpin" : "Pin"}
                    </Button>
                    <Button variant="ghost" size="sm" className="text-destructive"
                      onClick={() => act(() => api(`/memories/${m.id}`, { method: "DELETE" }), "Forgotten.")}>
                      Forget
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
