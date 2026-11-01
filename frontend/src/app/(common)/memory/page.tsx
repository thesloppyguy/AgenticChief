"use client";
import { useState } from "react";
import { Settings } from "lucide-react";
import { toast } from "sonner";
import { Card, Loading, PageHeader } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { label } from "@/lib/format";
import type { MemoryList } from "@/lib/types";

type Tab = "episodic" | "history";

interface HistoryNote {
  id: number;
  kind: string;
  summary: string;
  quote: string;
  due_at: string | null;
  pinned: boolean;
  correction: string | null;
  created_at: string;
}

interface HistoryList {
  enabled: boolean;
  notes: HistoryNote[];
}

export default function MemoryPage() {
  const [tab, setTab] = useState<Tab>("episodic");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const episodic = useApi<MemoryList>("/memories");
  const history = useApi<HistoryList>("/memories/history");
  const [corrections, setCorrections] = useState<Record<number, string>>({});

  async function act(fn: () => Promise<unknown>, ok: string, reload: () => void) {
    try {
      await fn();
      toast.success(ok);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Memory Store"
        subtitle="Episodic decisions the Executive extracts, plus private always-in-the-loop notes grounded in your own words."
        actions={
          <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
            <DialogTrigger
              render={
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label="Memory settings"
                />
              }
            >
              <Settings className="size-4" />
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Settings</DialogTitle>
                <DialogDescription>
                  Control what the Executive keeps from your conversations.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-5">
                {episodic.data && (
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id="enabled"
                      checked={episodic.data.enabled}
                      onCheckedChange={(checked) =>
                        act(
                          () =>
                            api("/memories/settings", {
                              method: "PUT",
                              body: JSON.stringify({ enabled: Boolean(checked) }),
                            }),
                          Boolean(checked) ? "Memory is on." : "Memory is off.",
                          episodic.reload,
                        )
                      }
                    />
                    <div>
                      <label htmlFor="enabled" className="text-sm font-medium">
                        Let the Executive remember
                      </label>
                      <p className="text-xs text-muted-foreground">
                        Memories expire unless you pin them. Turning this off stops new ones being
                        written; it does not delete what is already here.
                      </p>
                    </div>
                  </div>
                )}

                {history.data && (
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id="history-enabled"
                      checked={history.data.enabled}
                      onCheckedChange={(checked) =>
                        act(
                          () =>
                            api("/memories/history/settings", {
                              method: "PUT",
                              body: JSON.stringify({ enabled: Boolean(checked) }),
                            }),
                          Boolean(checked) ? "History notes on." : "History notes off.",
                          history.reload,
                        )
                      }
                    />
                    <div>
                      <label htmlFor="history-enabled" className="text-sm font-medium">
                        Keep track of what happens
                      </label>
                      <p className="text-xs text-muted-foreground">
                        Private notes grounded in your own words. Correct, pin, or forget anytime.
                      </p>
                    </div>
                  </div>
                )}

                {!episodic.data && !history.data && (
                  <p className="text-sm text-muted-foreground">Loading settings…</p>
                )}
              </div>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="flex gap-2">
        <Button
          size="sm"
          variant={tab === "episodic" ? "default" : "outline"}
          className="rounded-full"
          onClick={() => setTab("episodic")}
        >
          Episodic
        </Button>
        <Button
          size="sm"
          variant={tab === "history" ? "default" : "outline"}
          className="rounded-full"
          onClick={() => setTab("history")}
        >
          History notes
        </Button>
      </div>

      {tab === "episodic" && (
        <>
          <Loading error={episodic.error} loading={episodic.loading && !episodic.data} />
          {episodic.data && (
            <Card
              title={`Remembered (${episodic.data.memories.length})`}
              action={
                episodic.data.memories.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() =>
                      window.confirm("Forget everything?") &&
                      act(
                        () => api("/memories", { method: "DELETE" }),
                        "All forgotten.",
                        episodic.reload,
                      )
                    }
                  >
                    Forget all
                  </Button>
                )
              }
            >
              {episodic.data.memories.length === 0 && (
                <p className="text-sm text-muted-foreground">Nothing remembered yet.</p>
              )}
              <ul className="divide-y">
                {episodic.data.memories.map((m) => (
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
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          act(
                            () => api(`/memories/${m.id}/pin`, { method: "POST" }),
                            m.pinned ? "Unpinned." : "Pinned — it will not expire.",
                            episodic.reload,
                          )
                        }
                      >
                        {m.pinned ? "Unpin" : "Pin"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() =>
                          act(
                            () => api(`/memories/${m.id}`, { method: "DELETE" }),
                            "Forgotten.",
                            episodic.reload,
                          )
                        }
                      >
                        Forget
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}

      {tab === "history" && (
        <>
          <Loading error={history.error} loading={history.loading && !history.data} />
          {history.data && (
            <Card title={`Notes (${history.data.notes.length})`}>
              {history.data.notes.length === 0 && (
                <p className="text-sm text-muted-foreground">No history notes yet.</p>
              )}
              <ul className="divide-y">
                {history.data.notes.map((n) => (
                  <li key={n.id} className="space-y-2 py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{label(n.kind)}</Badge>
                      {n.pinned && <Badge variant="secondary">Pinned</Badge>}
                      {n.due_at && (
                        <span className="text-xs text-muted-foreground">
                          due {new Date(n.due_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    <p>{n.correction || n.summary}</p>
                    <p className="text-xs italic text-muted-foreground">&ldquo;{n.quote}&rdquo;</p>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        className="max-w-sm"
                        placeholder="Correct this note…"
                        value={corrections[n.id] ?? ""}
                        onChange={(e) =>
                          setCorrections((c) => ({ ...c, [n.id]: e.target.value }))
                        }
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          act(
                            () =>
                              api(`/memories/history/${n.id}`, {
                                method: "PATCH",
                                body: JSON.stringify({
                                  correction: corrections[n.id] || null,
                                }),
                              }),
                            "Corrected.",
                            history.reload,
                          )
                        }
                      >
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          act(
                            () =>
                              api(`/memories/history/${n.id}`, {
                                method: "PATCH",
                                body: JSON.stringify({ pinned: !n.pinned }),
                              }),
                            n.pinned ? "Unpinned." : "Pinned.",
                            history.reload,
                          )
                        }
                      >
                        {n.pinned ? "Unpin" : "Pin"}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive"
                        onClick={() =>
                          act(
                            () => api(`/memories/history/${n.id}`, { method: "DELETE" }),
                            "Forgotten.",
                            history.reload,
                          )
                        }
                      >
                        Forget
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
