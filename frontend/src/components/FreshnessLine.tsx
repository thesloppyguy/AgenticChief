"use client";

import type { SourceFreshness } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  fresh: "text-emerald-700 dark:text-emerald-400",
  stale: "text-amber-700 dark:text-amber-400",
  never: "text-destructive",
  partial: "text-amber-700 dark:text-amber-400",
};

export function FreshnessLine({ freshness }: { freshness?: SourceFreshness | null }) {
  if (!freshness) return null;
  const { overall, counts, sla_hours, mock_sources_enabled } = freshness;
  const parts = [
    counts.fresh ? `${counts.fresh} fresh` : null,
    counts.stale ? `${counts.stale} stale` : null,
    counts.never ? `${counts.never} never synced` : null,
  ].filter(Boolean);
  return (
    <p className={cn("text-sm", TONE[overall] ?? "text-muted-foreground")}>
      Data freshness: {overall}
      {parts.length ? ` (${parts.join(", ")})` : ""} · SLA {sla_hours}h
      {mock_sources_enabled ? " · AI-backed mock sources on" : " · stub fixture mode"}
    </p>
  );
}
