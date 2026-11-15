"use client";

import Link from "next/link";
import { Card } from "@/components/ui";
import { Button } from "@/components/ui/button";
import { friendlyRef } from "@/lib/format";
import { cn } from "@/lib/utils";

type Brief = {
  id: number;
  title: string;
  body: string;
  kind: string;
};

type BriefSection = {
  title: string;
  items: string[];
};

type ParsedItem =
  | { kind: "red"; code: string; score: string | null; label: string }
  | { kind: "approval"; id: string; action: string }
  | { kind: "text"; text: string };

function parseBriefBody(body: string): { heading?: string; sections: BriefSection[] } {
  const sections: BriefSection[] = [];
  let heading: string | undefined;
  let current: BriefSection | null = null;

  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("# ")) {
      heading = line.slice(2).trim();
      continue;
    }
    if (line.startsWith("## ")) {
      current = { title: line.slice(3).trim(), items: [] };
      sections.push(current);
      continue;
    }
    if (line.startsWith("- ") && current) {
      current.items.push(line.slice(2).trim());
    }
  }

  return { heading, sections };
}

function isEmptyItem(item: string): boolean {
  const t = item.toLowerCase();
  return (
    t === "clear." ||
    t === "none." ||
    t === "none pending." ||
    t === "quiet." ||
    t === "nothing red right now." ||
    t.startsWith("none")
  );
}

function polishScore(raw: string): string {
  const n = Number(raw);
  return Number.isFinite(n) ? n.toFixed(1) : raw;
}

function parseItem(item: string): ParsedItem {
  const red = item.match(
    /^([A-Z0-9._-]+)\s+is red\s*\(([^)]+)\)\s*$/i,
  );
  if (red) {
    return {
      kind: "red",
      code: red[1],
      score: polishScore(red[2]),
      label: "Off track",
    };
  }

  const groupRed = item.match(/^Group score\s+([\d.]+)\s+is red$/i);
  if (groupRed) {
    return {
      kind: "red",
      code: "Group",
      score: polishScore(groupRed[1]),
      label: "Off track",
    };
  }

  const approval = item.match(/^#(\d+)\s+(.+)$/);
  if (approval) {
    return {
      kind: "approval",
      id: approval[1],
      action: friendlyRef(approval[2].trim().replaceAll(" ", "_")),
    };
  }

  return {
    kind: "text",
    text: item.replace(/\((\d+\.\d{2})\d+\)/g, "($1)"),
  };
}

function kindMeta(kind: string): { label: string; dateFromTitle: boolean } {
  if (kind === "morning_brief") return { label: "Morning brief", dateFromTitle: true };
  if (kind === "end_of_day_digest") return { label: "End of day", dateFromTitle: true };
  return { label: "Brief", dateFromTitle: false };
}

function formatBriefDate(title: string): string | null {
  const m = title.match(/(\d{4}-\d{2}-\d{2})/);
  if (!m) return null;
  const d = new Date(`${m[1]}T12:00:00`);
  if (Number.isNaN(d.getTime())) return m[1];
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function sectionKey(title: string): "red" | "approvals" | "alerts" | "loops" | "other" {
  const t = title.toLowerCase();
  if (t.includes("red") || t.includes("scorecard")) return "red";
  if (t.includes("approval")) return "approvals";
  if (t.includes("alert")) return "alerts";
  if (t.includes("loop") || t.includes("noted") || t.includes("notes")) return "loops";
  return "other";
}

function StatChip({
  label,
  count,
  tone,
  hideCount,
}: {
  label: string;
  count?: number;
  tone: "danger" | "attention" | "ok" | "muted";
  hideCount?: boolean;
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium",
        tone === "danger" && "bg-destructive/10 text-destructive",
        tone === "attention" && "bg-warning/15 text-warning",
        tone === "ok" && "bg-[rgba(15,98,77,0.12)] text-[#0F624D]",
        tone === "muted" && "bg-muted text-muted-foreground",
      )}
    >
      {!hideCount && count != null && (
        <span className="tabular-nums font-semibold">{count}</span>
      )}
      <span className="opacity-90">{label}</span>
    </div>
  );
}

function ItemRow({ item }: { item: ParsedItem }) {
  if (item.kind === "red") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl bg-card/80 px-3 py-2.5 ring-1 ring-destructive/15">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="size-2 shrink-0 rounded-full bg-destructive" />
          <span className="truncate font-semibold tracking-tight">{item.code}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {item.score != null && (
            <span className="text-sm font-semibold tabular-nums text-foreground">
              {item.score}
            </span>
          )}
          <span className="rounded-md bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive">
            {item.label}
          </span>
        </div>
      </div>
    );
  }

  if (item.kind === "approval") {
    return (
      <Link
        href="/actions"
        className="group flex items-center justify-between gap-3 rounded-xl bg-card/80 px-3 py-2.5 ring-1 ring-warning/20 transition-colors hover:bg-card hover:ring-warning/40"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="font-mono text-[11px] text-muted-foreground">#{item.id}</span>
          <span className="truncate text-sm font-medium capitalize group-hover:text-foreground">
            {item.action}
          </span>
        </div>
        <span className="shrink-0 text-[11px] font-medium text-warning opacity-80 group-hover:opacity-100">
          Review
        </span>
      </Link>
    );
  }

  return (
    <div className="rounded-xl bg-card/70 px-3 py-2.5 text-sm leading-snug ring-1 ring-border/70">
      {item.text}
    </div>
  );
}

function SectionBlock({
  title,
  items,
  tone,
  className,
}: {
  title: string;
  items: string[];
  tone: "danger" | "attention" | "neutral";
  className?: string;
}) {
  const parsed = items.map(parseItem);

  return (
    <section className={cn("min-w-0 space-y-2.5", className)}>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "size-1.5 rounded-full",
            tone === "danger" && "bg-destructive",
            tone === "attention" && "bg-warning",
            tone === "neutral" && "bg-muted-foreground/50",
          )}
        />
        <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          {title}
        </h3>
        <span className="text-[11px] tabular-nums text-muted-foreground/80">
          {parsed.length}
        </span>
      </div>
      <div className="space-y-2">
        {parsed.map((item, i) => (
          <ItemRow
            key={
              item.kind === "approval"
                ? `a-${item.id}`
                : item.kind === "red"
                  ? `r-${item.code}-${item.score}`
                  : `t-${i}-${item.text}`
            }
            item={item}
          />
        ))}
      </div>
    </section>
  );
}

export function BriefCard({ brief }: { brief: Brief }) {
  const meta = kindMeta(brief.kind);
  const dateLabel = formatBriefDate(brief.title);
  const { sections } = parseBriefBody(brief.body);

  const buckets = {
    red: [] as BriefSection[],
    approvals: [] as BriefSection[],
    alerts: [] as BriefSection[],
    loops: [] as BriefSection[],
    other: [] as BriefSection[],
  };

  for (const section of sections) {
    buckets[sectionKey(section.title)].push(section);
  }

  const meaningful = (s: BriefSection) =>
    s.items.map((i) => i.trim()).filter((i) => i && !isEmptyItem(i));

  const redItems = buckets.red.flatMap(meaningful);
  const approvalItems = buckets.approvals.flatMap(meaningful);
  const alertItems = buckets.alerts.flatMap(meaningful);
  const loopItems = buckets.loops.flatMap(meaningful);
  const otherSections = buckets.other
    .map((s) => ({ ...s, items: meaningful(s) }))
    .filter((s) => s.items.length > 0);

  const hasAttention =
    redItems.length > 0 ||
    approvalItems.length > 0 ||
    alertItems.length > 0 ||
    otherSections.length > 0;

  return (
    <Card
      title={meta.label}
      action={
        <div className="flex flex-wrap items-center gap-2.5">
          {dateLabel && (
            <span className="text-sm text-muted-foreground">{dateLabel}</span>
          )}
          {approvalItems.length > 0 && (
            <Button
              size="sm"
              className="h-8 rounded-full px-3.5"
              render={<Link href="/actions" />}
              nativeButton={false}
            >
              Review approvals
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <StatChip
            count={redItems.length}
            label="still red"
            tone={redItems.length ? "danger" : "ok"}
          />
          <StatChip
            count={approvalItems.length}
            label={
              approvalItems.length === 1 ? "approval waiting" : "approvals waiting"
            }
            tone={approvalItems.length ? "attention" : "ok"}
          />
          {alertItems.length > 0 && (
            <StatChip
              count={alertItems.length}
              label={alertItems.length === 1 ? "alert" : "alerts"}
              tone="attention"
            />
          )}
          {loopItems.length > 0 ? (
            <StatChip count={loopItems.length} label="open loops" tone="muted" />
          ) : (
            <StatChip label="Open loops clear" tone="ok" hideCount />
          )}
        </div>

        {hasAttention ? (
          <div className="grid gap-5 rounded-[1.15rem] bg-muted/55 p-3.5 sm:p-4 lg:grid-cols-2">
            {redItems.length > 0 && (
              <SectionBlock title="Still red" items={redItems} tone="danger" />
            )}
            {approvalItems.length > 0 && (
              <SectionBlock
                title="Approvals waiting"
                items={approvalItems}
                tone="attention"
                className={redItems.length === 0 ? "lg:col-span-2" : undefined}
              />
            )}
            {alertItems.length > 0 && (
              <SectionBlock title="Recent alerts" items={alertItems} tone="attention" />
            )}
            {loopItems.length > 0 && (
              <SectionBlock title="Open loops" items={loopItems} tone="neutral" />
            )}
            {otherSections.map((s) => (
              <SectionBlock
                key={s.title}
                title={s.title}
                items={s.items}
                tone="neutral"
              />
            ))}
          </div>
        ) : (
          <p className="rounded-[1.15rem] bg-muted/55 px-4 py-3.5 text-sm text-muted-foreground">
            Quiet close — nothing still red, and no approvals waiting.
          </p>
        )}
      </div>
    </Card>
  );
}
