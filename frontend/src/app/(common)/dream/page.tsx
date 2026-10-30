"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bot, CheckCircle2, CircleDashed, Download, FileBarChart, Loader2,
  ShieldCheck, Terminal, Workflow, XCircle, Eye,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TimelineItem, TimelinePage } from "@/lib/types";

const KIND_ICON: Record<string, typeof Bot> = {
  tool: Terminal, capability: Download, delegate: Bot, workflow_step: Workflow,
  ingestion_run: Download, approval: ShieldCheck, job_run: FileBarChart, watch_fired: Eye,
};

const STATUS_ICON = {
  ok: CheckCircle2, failed: XCircle, running: Loader2, pending: CircleDashed, skipped: CircleDashed,
};

const STATUS_STYLE: Record<string, string> = {
  ok: "text-success", failed: "text-destructive", running: "text-muted-foreground animate-spin",
  pending: "text-warning", skipped: "text-muted-foreground",
};

const FILTERS = [
  { value: "", label: "Everything" },
  { value: "tool,delegate,capability", label: "Copilot" },
  { value: "workflow_step", label: "Workflows" },
  { value: "approval", label: "Approvals" },
  { value: "ingestion_run,job_run", label: "Scheduled" },
  { value: "watch_fired", label: "Watches" },
];

function href(item: TimelineItem): string | null {
  if (!item.ref) return null;
  if (item.ref.type === "workflow_run") return `/reports/${item.ref.id}`;
  if (item.ref.type === "approval") return `/actions?id=${item.ref.id}`;
  return null;
}

function Row({ item }: { item: TimelineItem }) {
  const Icon = KIND_ICON[item.kind] ?? CircleDashed;
  const Status = STATUS_ICON[item.status] ?? CircleDashed;
  const link = href(item);
  const body = (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-background">
          <Icon className="size-4 text-muted-foreground" />
        </div>
        {/* the spine of the timeline */}
        <div className="mt-1 w-px flex-1 bg-border" />
      </div>
      <div className="min-w-0 flex-1 pb-6">
        <div className="flex flex-wrap items-center gap-2">
          <Status className={cn("size-3.5 shrink-0", STATUS_STYLE[item.status])} />
          <span className="text-sm font-medium">{item.title}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="tabular-nums">{new Date(item.at).toLocaleString()}</span>
          <span>·</span>
          <span>{item.actor}</span>
          <Badge variant="outline" className="text-[10px]">{label(item.kind)}</Badge>
          {item.period && <span className="tabular-nums">{item.period}</span>}
          {item.entity && <span>{item.entity}</span>}
        </div>
      </div>
    </div>
  );
  return link ? (
    <Link href={link} className="block rounded-lg transition-colors hover:bg-muted/40">{body}</Link>
  ) : body;
}

/** What to fetch next. A descriptor rather than a callback, so the effect only starts the request
 *  and every state change happens in an event handler or the promise continuation. */
interface Request { cursor: string | null; kinds: string; append: boolean }

export default function DreamPage() {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [req, setReq] = useState<Request>({ cursor: null, kinds: "", append: false });

  useEffect(() => {
    let live = true;
    const qs = new URLSearchParams({ limit: "40" });
    if (req.cursor) qs.set("cursor", req.cursor);
    if (req.kinds) qs.set("kinds", req.kinds);
    api<TimelinePage>(`/timeline?${qs}`)
      .then((page) => {
        if (!live) return;
        setItems((prev) => (req.append ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
        setDone(!page.next_cursor);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (!live) return;
        toast.error(e instanceof Error ? e.message : "Could not load the timeline");
        setDone(true);
        setLoading(false);
      });
    return () => { live = false; };
  }, [req]);

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Dream</h1>
          <p className="text-sm text-muted-foreground">
            Everything the agent did, newest first — whether you asked for it or a schedule set it off.
          </p>
        </div>
        <Select items={FILTERS} value={req.kinds}
          onValueChange={(v) => { setLoading(true); setReq({ cursor: null, kinds: String(v), append: false }); }}>
          <SelectTrigger size="sm" className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            {FILTERS.map((f) => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {loading && items.length === 0 && (
        <div className="space-y-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      )}

      {!loading && items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nothing yet. Ask the Copilot something, or run a workflow, and it will show up here.
        </p>
      )}

      <div>{items.map((i) => <Row key={i.id} item={i} />)}</div>

      {!done && items.length > 0 && (
        <Button variant="outline" disabled={loading}
          onClick={() => { setLoading(true); setReq({ cursor, kinds: req.kinds, append: true }); }}>
          {loading ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}
