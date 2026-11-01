"use client";

import { useState, type ReactNode } from "react";
import {
  BarChart3,
  Download,
  CalendarClock,
  Table2,
  Layers3,
  Crosshair,
  ListChecks,
  Activity,
} from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, download } from "@/lib/api";
import { fmt, label as pillarLabel, STATUS_TEXT } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Status } from "@/lib/types";
import type {
  ArtifactDraft,
  ArtifactHeadline,
  ArtifactIssue,
  ChatArtifact,
} from "./types";

/** Dashboard viz palette (reference HR reports) — distinct from Lokify orange chrome. */
const VIZ = {
  demand: "#364149",
  supply: "#0F624D",
  ready: "#0E6B57",
  pipeline: "#B8956A",
  gap: "#D4C9B8",
  teal: "#0F624D",
  tealSoft: "rgba(15, 98, 77, 0.12)",
  build: "#0E6B57",
  buy: "#C45C4A",
  ochre: "#B8956A",
  shell: "#F7F3EF",
};

const STATUS_COLOR: Record<string, string> = {
  green: "var(--success)",
  amber: "var(--warning)",
  red: "var(--destructive)",
};

const KIND_META: Record<string, { label: string; icon: typeof BarChart3 }> = {
  ic_compare: { label: "Comparison", icon: BarChart3 },
  kpi_bars: { label: "Sub-KPIs", icon: Table2 },
  scorecard_summary: { label: "Scorecard", icon: Layers3 },
  skills_demand_supply: { label: "Skills", icon: BarChart3 },
  succession_stack: { label: "Succession", icon: Layers3 },
  workforce_pulse: { label: "Pulse", icon: Activity },
  action_drafts: { label: "Decisions", icon: ListChecks },
  table: { label: "Table", icon: Table2 },
};

function asStatus(v: string | undefined): Status {
  return v === "green" || v === "amber" || v === "red" ? v : null;
}

function score(n: number | null | undefined, digits = 1) {
  return fmt(n, digits);
}

function statusWord(s?: string | null) {
  if (!s) return null;
  if (s === "green" || s === "amber" || s === "red") return STATUS_TEXT[s];
  return s;
}

function toneClass(tone?: string) {
  if (tone === "good") return "text-[color:var(--success)]";
  if (tone === "alert") return "text-destructive";
  return "text-foreground";
}

function HeadlineStrip({
  items,
}: {
  items?: ArtifactHeadline[] | ChatArtifact["items"] | ChatArtifact["stats"];
}) {
  if (!items?.length) return null;
  return (
    <div
      className={cn(
        "grid gap-2",
        items.length >= 5
          ? "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5"
          : items.length === 4
            ? "grid-cols-2 sm:grid-cols-4"
            : items.length === 3
              ? "grid-cols-1 sm:grid-cols-3"
              : "grid-cols-2",
      )}
    >
      {items.map((h, i) => {
        const value = "value" in h ? h.value : undefined;
        const unit = "unit" in h ? h.unit : undefined;
        const note = "note" in h ? h.note : undefined;
        const label = "label" in h ? h.label : undefined;
        const tone = "tone" in h ? h.tone : undefined;
        const delta =
          "delta_pct" in h && h.delta_pct != null ? Number(h.delta_pct) : null;
        const dir =
          "delta_direction" in h ? h.delta_direction : undefined;
        const deltaUp = dir === "up" || (delta != null && delta > 0);
        const deltaDown = dir === "down" || (delta != null && delta < 0);
        return (
          <div
            key={`${label}-${i}`}
            className="rounded-xl border border-border/70 bg-background px-3 py-2.5 shadow-sm"
          >
            <div className="text-[11px] font-medium leading-snug text-muted-foreground">
              {label}
            </div>
            <div
              className={cn(
                "mt-1 text-xl font-semibold tabular-nums tracking-tight",
                toneClass(tone),
              )}
            >
              {typeof value === "number" ? score(value, value >= 100 ? 0 : 1) : (value ?? "—")}
              {unit ? (
                <span className="ml-0.5 text-sm font-medium text-muted-foreground">
                  {unit}
                </span>
              ) : null}
            </div>
            {(note || delta != null) && (
              <div
                className={cn(
                  "mt-0.5 text-[11px] leading-snug",
                  tone === "alert" || deltaDown
                    ? "text-destructive"
                    : deltaUp
                      ? "text-[color:var(--success)]"
                      : "text-muted-foreground",
                )}
              >
                {delta != null ? (
                  <>
                    {deltaUp ? "▲" : deltaDown ? "▼" : "·"}{" "}
                    {Math.abs(delta)}
                    {note ? ` ${note}` : ""}
                  </>
                ) : (
                  note
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Donut({
  value,
  max = 100,
  status,
  size = 88,
}: {
  value: number;
  max?: number;
  status?: string;
  size?: number;
}) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = Math.min(1, Math.max(0, value / max));
  const color = STATUS_COLOR[status || ""] || VIZ.teal;
  return (
    <svg width={size} height={size} viewBox="0 0 88 88" className="shrink-0">
      <circle
        cx="44"
        cy="44"
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="8"
        className="text-muted/80"
      />
      <circle
        cx="44"
        cy="44"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${pct * c} ${c}`}
        transform="rotate(-90 44 44)"
      />
      <text
        x="44"
        y="42"
        textAnchor="middle"
        className="fill-foreground"
        style={{ fontSize: 18, fontWeight: 650 }}
      >
        {Math.round(value)}
      </text>
      <text
        x="44"
        y="56"
        textAnchor="middle"
        className="fill-muted-foreground"
        style={{ fontSize: 10 }}
      >
        /{max}
      </text>
    </svg>
  );
}

function ThinBar({
  pct,
  color,
  className,
}: {
  pct: number;
  color: string;
  className?: string;
}) {
  const w = Math.min(100, Math.max(0, pct));
  return (
    <div className={cn("h-1.5 overflow-hidden rounded-full bg-muted", className)}>
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{ width: `${w}%`, background: color }}
      />
    </div>
  );
}

function SoftPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "alert" | "good" | "warn" | "teal";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
        tone === "alert" && "bg-destructive/10 text-destructive",
        tone === "good" && "bg-success/10 text-success",
        tone === "warn" && "bg-warning/15 text-warning",
        tone === "teal" && "bg-[rgba(15,98,77,0.12)] text-[#0F624D]",
        tone === "neutral" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function ScorecardBody({ artifact }: { artifact: ChatArtifact }) {
  const pillars = artifact.pillars || [];
  const overall = artifact.overall;
  const exceptions = artifact.exceptions || [];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="flex items-center gap-4 rounded-2xl border border-border/70 bg-[color:var(--shell)]/60 px-4 py-3">
          {overall != null ? (
            <Donut value={Number(overall)} status={artifact.status} />
          ) : null}
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-3xl font-semibold tabular-nums tracking-tight">
                {score(overall, 0)}
              </span>
              <StatusBadge status={asStatus(artifact.status)} />
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {artifact.subtitle ||
                (exceptions[0]
                  ? `${exceptions[0].title} (${score(exceptions[0].score, 0)}) is driving the gap.`
                  : "Group score across Independent Companies and pillars.")}
            </p>
          </div>
        </div>
        <HeadlineStrip items={artifact.stats} />
      </div>

      {exceptions.map((ex, i) => (
        <div
          key={i}
          className="rounded-2xl border border-destructive/25 bg-destructive/[0.06] px-4 py-3"
        >
          <div className="text-sm font-semibold text-destructive">
            Scorecard exception — {ex.title}
            {ex.score != null ? ` (${score(ex.score, 0)}, Red)` : ""}
          </div>
          {ex.detail ? (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {ex.detail}
            </p>
          ) : null}
        </div>
      ))}

      {pillars.length > 0 ? (
        <div>
          <div className="mb-2 text-sm font-semibold tracking-tight">
            Seven HR pillars
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {pillars.map((p) => {
              const st = p.status || "";
              const color = STATUS_COLOR[st] || VIZ.teal;
              const isRed = st === "red";
              return (
                <div
                  key={String(p.key || p.label)}
                  className={cn(
                    "rounded-xl border bg-background px-3 py-2.5 shadow-sm",
                    isRed
                      ? "border-destructive/40 ring-1 ring-destructive/15"
                      : "border-border/70",
                  )}
                >
                  <div className="text-sm font-semibold leading-snug">
                    {p.label || pillarLabel(String(p.key || ""))}
                  </div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    {p.weight != null ? `Weight ${score(p.weight, 0)}%` : null}
                    {p.weight != null && p.kpi_count != null ? " · " : null}
                    {p.kpi_count != null ? `${p.kpi_count} KPIs` : null}
                  </div>
                  <div className="mt-2 flex items-baseline gap-1.5">
                    <span
                      className="size-1.5 shrink-0 rounded-full"
                      style={{ background: color }}
                    />
                    <span className="text-2xl font-semibold tabular-nums tracking-tight">
                      {score(p.score, 0)}
                    </span>
                  </div>
                  <ThinBar
                    pct={Number(p.score) || 0}
                    color={color}
                    className="mt-2"
                  />
                  <div className="mt-1.5 text-[11px] text-muted-foreground">
                    {statusWord(st) || "—"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function KpiTableBody({ artifact }: { artifact: ChatArtifact }) {
  const items = artifact.items || [];
  const rich = items.some(
    (i) => i.target != null || i.actual != null || i.weight != null,
  );
  if (!rich) {
    const max = Math.max(...items.map((i) => Number(i.value) || 0), 1);
    return (
      <div className="space-y-3">
        {items.map((i, idx) => (
          <div key={String(i.label)} className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                {artifact.kind === "ic_compare" ? (
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-muted text-[10px] font-semibold tabular-nums text-muted-foreground">
                    {idx + 1}
                  </span>
                ) : null}
                <span className="truncate text-sm font-medium">{i.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tabular-nums">
                  {score(i.value)}
                  {i.unit || ""}
                </span>
                {i.status ? <StatusBadge status={asStatus(i.status)} /> : null}
              </div>
            </div>
            <ThinBar
              pct={((Number(i.value) || 0) / max) * 100}
              color={STATUS_COLOR[i.status || ""] || VIZ.teal}
            />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border/80">
      <table className="w-full min-w-[36rem] text-left text-sm">
        <thead>
          <tr className="border-b border-border/70 bg-muted/40 text-[11px] text-muted-foreground">
            <th className="px-3 py-2.5 font-semibold">Sub-KPI</th>
            <th className="px-3 py-2.5 text-right font-semibold">Target</th>
            <th className="px-3 py-2.5 text-right font-semibold">Actual</th>
            <th className="px-3 py-2.5 text-right font-semibold">Score</th>
            <th className="px-3 py-2.5 text-right font-semibold">Weight</th>
            <th className="px-3 py-2.5 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => {
            const color = STATUS_COLOR[i.status || ""] || VIZ.ochre;
            const barPct = Number(i.value) || 0;
            return (
              <tr key={String(i.label)} className="border-t border-border/60">
                <td className="px-3 py-3 align-top">
                  <div className="font-semibold leading-snug">{i.label}</div>
                  {i.note ? (
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {i.note}
                    </div>
                  ) : null}
                  {i.tags?.length ? (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {i.tags.map((t) => (
                        <SoftPill key={t}>{t}</SoftPill>
                      ))}
                    </div>
                  ) : null}
                  <ThinBar pct={barPct} color={color} className="mt-2 max-w-[14rem]" />
                </td>
                <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                  {i.target != null ? `${score(i.target, 0)}%` : "—"}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {i.actual != null ? `${score(i.actual, 0)}%` : "—"}
                </td>
                <td className="px-3 py-3 text-right text-base font-semibold tabular-nums">
                  {score(i.value, 0)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                  {i.weight != null ? `${score(i.weight, 0)}%` : "—"}
                </td>
                <td className="px-3 py-3">
                  {i.status ? <StatusBadge status={asStatus(i.status)} /> : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function InsightList({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <ul className="space-y-1.5 rounded-xl border border-border/70 bg-muted/30 px-3.5 py-3 text-xs leading-relaxed text-muted-foreground">
      {items.map((line) => (
        <li key={line} className="flex gap-2">
          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[#0F624D]" />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

function ExceptionBanner({
  exceptions,
}: {
  exceptions?: ChatArtifact["exceptions"];
}) {
  if (!exceptions?.length) return null;
  return (
    <div className="space-y-2">
      {exceptions.map((ex, i) => (
        <div
          key={i}
          className="rounded-2xl border border-destructive/25 bg-destructive/[0.06] px-4 py-3"
        >
          <div className="text-sm font-semibold text-destructive">
            {ex.title || "Scorecard exception"}
            {ex.score != null && !String(ex.title || "").includes(String(ex.score))
              ? ` (${score(ex.score, 0)}, Red)`
              : ""}
          </div>
          {ex.detail ? (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {ex.detail}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function IssueCards({ issues }: { issues: ArtifactIssue[] }) {
  if (!issues.length) return null;
  return (
    <div className="space-y-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight">
          The {issues.length} issues needing your attention
        </h3>
      </div>
      <div className="space-y-2">
        {issues.map((issue) => {
          const high =
            issue.severity === "high" ||
            issue.severity === "urgent" ||
            (issue.rank != null && issue.rank <= 2);
          const priority = issue.priority_label || (high ? "High" : "Medium");
          return (
            <div
              key={`${issue.rank}-${issue.title}`}
              className={cn(
                "rounded-xl border border-border/70 bg-background py-3 pl-3 pr-4 shadow-sm",
                "border-l-[3px]",
                high ? "border-l-destructive" : "border-l-warning",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <SoftPill tone={high ? "alert" : "warn"}>
                  <span
                    className={cn(
                      "mr-1.5 inline-block size-1.5 rounded-full",
                      high ? "bg-destructive" : "bg-warning",
                    )}
                  />
                  {priority}
                </SoftPill>
                {issue.rank != null ? (
                  <span className="text-[10px] tabular-nums text-muted-foreground">
                    #{issue.rank}
                  </span>
                ) : null}
              </div>
              <div className="mt-1.5 text-sm font-semibold leading-snug">
                {issue.title}
              </div>
              {issue.summary ? (
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {issue.summary}
                </p>
              ) : null}
              {issue.tags?.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {issue.tags.map((t) => (
                    <SoftPill key={t}>{t}</SoftPill>
                  ))}
                </div>
              ) : null}
              {issue.recommendation ? (
                <p className="mt-2 text-xs leading-relaxed">
                  <span className="font-semibold">Recommended path: </span>
                  {issue.recommendation}
                </p>
              ) : null}
              {issue.flagged_by?.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {issue.flagged_by.map((f) => (
                    <SoftPill key={f} tone="teal">
                      {f}
                    </SoftPill>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SkillsBody({ artifact }: { artifact: ChatArtifact }) {
  const domains = artifact.domains || [];
  const maxDemand = Math.max(...domains.map((d) => Number(d.demand) || 0), 1);
  const bvb = artifact.build_vs_buy;
  const capacity = artifact.capacity || [];
  const mobility = artifact.mobility || [];

  return (
    <div className="space-y-4">
      <HeadlineStrip items={artifact.headline} />
      <InsightList items={artifact.insights} />

      {domains.length > 0 ? (
        <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
          <div className="text-sm font-semibold">By domain · next 24 months</div>
          {artifact.subtitle ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{artifact.subtitle}</p>
          ) : null}
          <div className="mt-4 space-y-3.5">
            {domains.map((d) => {
              const demand = Number(d.demand) || 0;
              const supply = Number(d.supply) || 0;
              return (
                <div key={String(d.label)} className="space-y-1">
                  <div className="text-sm font-medium">{d.label}</div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[#EDE6DC]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${(demand / maxDemand) * 100}%`,
                            background: VIZ.demand,
                          }}
                        />
                      </div>
                      <span className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums">
                        {score(demand, 0)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[#EDE6DC]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${(supply / maxDemand) * 100}%`,
                            background: VIZ.supply,
                          }}
                        />
                      </div>
                      <span className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums text-[#0F624D]">
                        {score(supply, 0)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{ background: VIZ.demand }}
              />{" "}
              Demand (roles)
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{ background: VIZ.supply }}
              />{" "}
              Projected supply
            </span>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        {bvb?.metrics?.length ? (
          <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
            <div className="text-sm font-semibold">Build vs buy</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {bvb.insight ||
                `${bvb.focus || "Strategic skills"} — for scarce skills, building internally wins on cost, speed and retention.`}
            </p>
            <div className="mt-3 space-y-3">
              {bvb.metrics.map((m) => {
                const build = Number(m.build) || 0;
                const buy = Number(m.buy) || 0;
                const max = Math.max(build, buy, 1);
                return (
                  <div key={String(m.label)} className="space-y-1.5">
                    <div className="text-xs font-medium text-muted-foreground">
                      {m.label}
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="w-24 shrink-0 text-[11px]">Build</span>
                        <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${(build / max) * 100}%`,
                              background: VIZ.build,
                            }}
                          />
                        </div>
                        <span className="w-8 text-right text-xs font-semibold tabular-nums">
                          {score(build, 0)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-24 shrink-0 text-[11px]">Buy</span>
                        <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${(buy / max) * 100}%`,
                              background:
                                buy > build ? VIZ.buy : VIZ.ochre,
                            }}
                          />
                        </div>
                        <span className="w-8 text-right text-xs font-semibold tabular-nums">
                          {score(buy, 0)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {capacity.length > 0 ? (
          <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
            <div className="text-sm font-semibold">Internal build capacity</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {artifact.capacity_insight ||
                "Adjacent-skill engineers who can reskill into future-critical roles."}
            </p>
            <div className="mt-3 space-y-2">
              {capacity.map((c) => {
                const n = Number(c.candidates) || 0;
                const max = Math.max(
                  ...capacity.map((x) => Number(x.candidates) || 0),
                  1,
                );
                return (
                  <div key={`${c.from}-${c.to}`} className="space-y-1">
                    <div className="flex justify-between gap-2 text-xs">
                      <span className="font-medium">
                        {c.from} → {c.to}
                      </span>
                      <span className="font-semibold tabular-nums text-[#0F624D]">
                        {score(n, 0)}
                      </span>
                    </div>
                    <ThinBar
                      pct={(n / max) * 100}
                      color={VIZ.supply}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>

      {domains.some((d) => d.path || d.gap != null) ? (
        <div className="overflow-x-auto rounded-xl border border-border/80">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead>
              <tr className="border-b border-border/70 bg-muted/40 text-[11px] text-muted-foreground">
                <th className="px-3 py-2.5 font-semibold">Domain</th>
                <th className="px-3 py-2.5 text-right font-semibold">Demand</th>
                <th className="px-3 py-2.5 text-right font-semibold">Supply</th>
                <th className="px-3 py-2.5 text-right font-semibold">Gap</th>
                <th className="px-3 py-2.5 font-semibold">Recommended path</th>
              </tr>
            </thead>
            <tbody>
              {domains.map((d) => {
                const gap = Number(d.gap) || 0;
                const path = String(d.path || "");
                const pathLabel =
                  path === "build"
                    ? "Build internally"
                    : path === "blend"
                      ? "Blend internally"
                      : path || "—";
                return (
                  <tr key={String(d.label)} className="border-t border-border/60">
                    <td className="px-3 py-2.5 font-medium">{d.label}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {score(d.demand, 0)}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      {score(d.supply, 0)}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2.5 text-right font-semibold tabular-nums",
                        gap >= 300
                          ? "text-destructive"
                          : gap >= 150
                            ? "text-warning"
                            : "text-foreground",
                      )}
                    >
                      {score(gap, 0)}
                    </td>
                    <td className="px-3 py-2.5">
                      <SoftPill
                        tone={path === "build" ? "good" : path === "blend" ? "warn" : "neutral"}
                      >
                        {pathLabel}
                      </SoftPill>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {mobility.length > 0 ? (
        <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
          <div className="text-sm font-semibold">Internal mobility opportunities</div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {artifact.mobility_insight ||
              "High-potential engineers whose adjacent skills make them candidates for future-critical businesses."}
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {mobility.map((m) => (
              <div key={String(m.label)}>
                <div className="text-[11px] leading-snug text-muted-foreground">
                  {m.label}
                </div>
                <div className="mt-0.5 text-xl font-semibold tabular-nums text-[#0F624D]">
                  {score(m.count, 0)}{" "}
                  <span className="text-xs font-medium text-muted-foreground">
                    candidates
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SuccessionBody({ artifact }: { artifact: ChatArtifact }) {
  const functions = artifact.functions || [];
  const bench = artifact.bench || [];
  const maxTotal = Math.max(
    ...functions.map(
      (f) =>
        (Number(f.ready_now) || 0) +
        (Number(f.ready_1_2y) || 0) +
        (Number(f.no_successor) || 0),
    ),
    1,
  );

  return (
    <div className="space-y-4">
      <HeadlineStrip items={artifact.headline} />
      <InsightList items={artifact.insights} />

      {functions.length > 0 ? (
        <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
          <div className="text-sm font-semibold">{artifact.title}</div>
          {artifact.subtitle ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{artifact.subtitle}</p>
          ) : null}
          <div className="mt-4 space-y-3">
            {functions.map((f) => {
              const ready = Number(f.ready_now) || 0;
              const pipe = Number(f.ready_1_2y) || 0;
              const gap = Number(f.no_successor) || 0;
              const total = ready + pipe + gap || 1;
              const scale = (total / maxTotal) * 100;
              return (
                <div key={String(f.function)} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="inline-flex flex-wrap items-center gap-1.5 text-sm font-medium">
                      {f.function}
                      {f.is_new ? <SoftPill tone="warn">new</SoftPill> : null}
                    </span>
                    <span className="text-[11px] tabular-nums text-muted-foreground">
                      {ready} · {pipe} · {gap}
                    </span>
                  </div>
                  <div
                    className="flex h-3 overflow-hidden rounded-full bg-muted"
                    style={{ width: `${Math.max(28, scale)}%` }}
                  >
                    <div
                      className="h-full border-r border-white/80"
                      style={{
                        width: `${(ready / total) * 100}%`,
                        background: VIZ.ready,
                      }}
                      title={`Ready now: ${ready}`}
                    />
                    <div
                      className="h-full border-r border-white/80"
                      style={{
                        width: `${(pipe / total) * 100}%`,
                        background: VIZ.pipeline,
                      }}
                      title={`Ready 1–2y: ${pipe}`}
                    />
                    <div
                      className="h-full"
                      style={{
                        width: `${(gap / total) * 100}%`,
                        background: VIZ.gap,
                      }}
                      title={`No successor: ${gap}`}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: VIZ.ready }} />{" "}
              Ready now
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{ background: VIZ.pipeline }}
              />{" "}
              Ready in 1–2 years
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: VIZ.gap }} />{" "}
              No successor
            </span>
          </div>
        </div>
      ) : null}

      {bench.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-border/80">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead>
              <tr className="border-b border-border/70 bg-muted/40 text-[11px] text-muted-foreground">
                <th className="px-3 py-2.5 font-semibold">Critical role</th>
                <th className="px-3 py-2.5 font-semibold">Readiness</th>
                <th className="px-3 py-2.5 font-semibold">Best internal successor</th>
                <th className="px-3 py-2.5 font-semibold">Development move</th>
              </tr>
            </thead>
            <tbody>
              {bench.map((b) => {
                const pct = Number(b.ready_pct) || 0;
                const color =
                  pct >= 75 ? VIZ.ready : pct >= 50 ? VIZ.ochre : "var(--destructive)";
                return (
                  <tr key={String(b.role)} className="border-t border-border/60">
                    <td className="px-3 py-3">
                      <div className="font-semibold leading-snug">{b.role}</div>
                      {b.business ? (
                        <div className="mt-0.5 text-[11px] text-muted-foreground">
                          {b.business}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <ThinBar pct={pct} color={color} className="w-24" />
                        <span className="text-xs font-semibold tabular-nums">
                          {score(pct, 0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-muted-foreground">
                      {b.successor || b.note || b.status || "—"}
                    </td>
                    <td className="px-3 py-3 text-xs text-foreground">
                      {b.development_move || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

const PIPELINE = [
  "Observe",
  "Analyze",
  "Recommend",
  "Approve",
  "Execute",
  "Track",
] as const;

function DecisionStepper({ active = 2 }: { active?: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-y-2">
      {PIPELINE.map((step, i) => {
        const done = i < active;
        const current = i === active;
        return (
          <li key={step} className="flex items-center">
            <div className="flex items-center gap-1.5">
              <span
                className={cn(
                  "flex size-5 items-center justify-center rounded-full text-[10px] font-semibold",
                  done && "bg-[#0F624D] text-white",
                  current &&
                    "border-2 border-[#0F624D] bg-background text-[#0F624D]",
                  !done && !current && "bg-muted text-muted-foreground",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "text-[11px]",
                  current || done
                    ? "font-medium text-foreground"
                    : "text-muted-foreground",
                )}
              >
                {step}
              </span>
            </div>
            {i < PIPELINE.length - 1 ? (
              <span className="mx-2 h-px w-4 bg-border sm:w-6" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function DraftCard({ draft }: { draft: ArtifactDraft }) {
  const roi = draft.roi;
  const body = draft.detail || draft.summary;
  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg"
          style={{ background: VIZ.tealSoft, color: VIZ.teal }}
        >
          <Crosshair className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold leading-snug text-[#0F624D]">
              {draft.title}
            </h3>
            {draft.sla ? <SoftPill tone="warn">{draft.sla}</SoftPill> : null}
          </div>
          {body ? (
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              {body}
            </p>
          ) : null}
          {draft.drivers?.length ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {draft.drivers.map((d) => (
                <SoftPill key={d}>{d}</SoftPill>
              ))}
            </div>
          ) : null}
          {draft.routes_to?.length ? (
            <div className="mt-2 text-[11px] text-muted-foreground">
              Routes to {draft.routes_to.join(", ")}
            </div>
          ) : null}
        </div>
      </div>
      {draft.insights?.length ? (
        <div className="mt-3">
          <InsightList items={draft.insights} />
        </div>
      ) : null}

      {roi ? (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <div className="text-[10px] text-muted-foreground">Programme cost</div>
            <div className="text-sm font-semibold tabular-nums">
              ≈ ₹{score(roi.programme_cost_cr, 1)} Cr
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground">
              Avoided hiring premium
            </div>
            <div className="text-sm font-semibold tabular-nums text-[#0F624D]">
              ≈ ₹{score(roi.avoided_hiring_premium_cr, 0)} Cr
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground">Gap closed</div>
            <div className="text-sm font-semibold tabular-nums">
              ~{score(roi.gap_closed_pct, 0)}%
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground">
              Time to productivity
            </div>
            <div className="text-sm font-semibold tabular-nums">
              {score(roi.time_to_productivity_mo, 0)} mo
              {roi.buy_time_to_productivity_mo != null
                ? ` vs ${score(roi.buy_time_to_productivity_mo, 0)}`
                : ""}
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-4">
        <DecisionStepper active={2} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          className="h-8 rounded-lg bg-[#0F624D] text-white hover:bg-[#0c513f]"
          onClick={() =>
            toast.message("Open Actions to approve", {
              description: draft.title,
            })
          }
        >
          Approve and execute
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-8 rounded-lg">
          Ask about this
        </Button>
      </div>
    </div>
  );
}

function ApprovalsList({ drafts }: { drafts: ArtifactDraft[] }) {
  if (drafts.length <= 1) return null;
  return (
    <div className="rounded-2xl border border-border/70 bg-background shadow-sm">
      <div className="border-b border-border/70 px-4 py-3">
        <div className="font-serif text-lg tracking-tight">Approvals</div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Nothing acts without you. Each recommended action pauses here for human
          approval, then executes across Learning, HRMS and Teams.
        </p>
      </div>
      <ul className="divide-y divide-border/70">
        {drafts.map((d) => (
          <li
            key={d.key || d.title}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">{d.title}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">
                {[
                  d.summary?.split(/[.;]/)[0],
                  d.routes_to?.length
                    ? `routes to ${d.routes_to.join(", ")}`
                    : d.channels?.length
                      ? `routes to ${d.channels.join(", ")}`
                      : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {d.sla ? <SoftPill tone="warn">{d.sla}</SoftPill> : null}
              <Button
                type="button"
                size="sm"
                className="h-8 rounded-lg bg-[#0F624D] text-white hover:bg-[#0c513f]"
                onClick={() =>
                  toast.message("Open Actions to approve", {
                    description: d.title,
                  })
                }
              >
                Approve
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ArtifactBody({ artifact }: { artifact: ChatArtifact }) {
  if (artifact.kind === "scorecard_summary") {
    return <ScorecardBody artifact={artifact} />;
  }
  if (artifact.kind === "workforce_pulse") {
    return (
      <div className="space-y-4">
        <HeadlineStrip items={artifact.items} />
        <ExceptionBanner exceptions={artifact.exceptions} />
        <InsightList items={artifact.insights} />
        <IssueCards issues={artifact.issues || []} />
      </div>
    );
  }
  if (artifact.kind === "skills_demand_supply") {
    return <SkillsBody artifact={artifact} />;
  }
  if (artifact.kind === "succession_stack") {
    return <SuccessionBody artifact={artifact} />;
  }
  if (artifact.kind === "action_drafts") {
    const drafts = artifact.drafts || [];
    return (
      <div className="space-y-3">
        {drafts.slice(0, 1).map((d) => (
          <DraftCard key={d.key || d.title} draft={d} />
        ))}
        <ApprovalsList drafts={drafts} />
      </div>
    );
  }
  if (
    (artifact.kind === "kpi_bars" || artifact.kind === "ic_compare") &&
    artifact.items?.length
  ) {
    return <KpiTableBody artifact={artifact} />;
  }
  if (artifact.kind === "table" && artifact.rows?.length) {
    return (
      <div className="overflow-x-auto rounded-xl border border-border/80">
        <table className="w-full min-w-[18rem] text-left text-sm">
          {artifact.columns?.length ? (
            <thead>
              <tr className="bg-muted/60 text-muted-foreground">
                {artifact.columns.map((c) => (
                  <th key={c} className="px-3 py-2 text-xs font-semibold">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {artifact.rows.map((row, i) => (
              <tr key={i} className="border-t border-border/70">
                {(row as unknown[]).map((cell, j) => (
                  <td key={j} className="px-3 py-2 tabular-nums">
                    {typeof cell === "number" ? score(cell) : String(cell ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <pre className="overflow-x-auto rounded-xl bg-muted/50 p-3 text-[11px] text-muted-foreground">
      {JSON.stringify(artifact, null, 2)}
    </pre>
  );
}

export function ChatArtifacts({
  artifacts,
  fullWidth = false,
}: {
  artifacts?: ChatArtifact[];
  /** Report pages: use the content column width. Chat keeps the 52rem bubble cap. */
  fullWidth?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  if (!artifacts?.length) return null;

  async function onExport(a: ChatArtifact) {
    const key = a.export_key;
    if (!key) return;
    setBusy(`export:${key}`);
    try {
      if (key === "scorecard") {
        await download("/reports/export/scorecard.csv", "scorecard.csv");
      } else {
        const kind = key.startsWith("workforce_")
          ? key.slice("workforce_".length)
          : key;
        await download(`/workforce/export/${kind}`, `workforce_${kind}.csv`);
      }
      toast.success("Export downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  async function onSchedule(a: ChatArtifact) {
    const reportKey = a.schedule_key;
    if (!reportKey) return;
    setBusy(`schedule:${reportKey}`);
    try {
      const out = await api<{
        verdict: string;
        reason?: string;
        approval?: { id: number };
      }>("/approvals", {
        method: "POST",
        body: JSON.stringify({
          action: "schedule_report",
          args: {
            report_key: reportKey,
            name: a.title || `Scheduled ${reportKey}`,
            cadence: { type: "weekly", weekday: 0, time: "07:00" },
            period: "current",
          },
          context: {
            reason: `Schedule from chat artifact: ${a.title || reportKey}`,
          },
        }),
      });
      if (out.verdict === "deny") {
        toast.error(out.reason || "Schedule denied by policy");
      } else {
        toast.success(
          out.approval?.id
            ? `Schedule proposed (#${out.approval.id}) — approve on Actions`
            : "Schedule proposed",
        );
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not schedule");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className={
        fullWidth
          ? "mt-1 w-full space-y-3"
          : "mt-1 w-full max-w-[min(100%,52rem)] space-y-3"
      }
    >
      {artifacts.map((a, i) => {
        const meta = KIND_META[a.kind] ?? {
          label: "Report",
          icon: BarChart3,
        };
        const Icon = meta.icon;
        return (
          <article
            key={`${a.kind}-${i}`}
            className="overflow-hidden rounded-2xl border border-border/80 bg-[color:var(--shell)]/35 shadow-md ring-1 ring-black/[0.03]"
          >
            <header className="flex items-center justify-between gap-3 border-b border-border/70 bg-background/80 px-4 py-2.5">
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[rgba(15,98,77,0.1)] text-[#0F624D]">
                  <Icon className="size-3.5" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold tracking-tight">
                    {a.title || meta.label}
                  </div>
                  {a.subtitle || a.source ? (
                    <div className="truncate text-[11px] text-muted-foreground">
                      {a.subtitle || a.source}
                    </div>
                  ) : null}
                </div>
              </div>
              <Badge
                variant="outline"
                className="shrink-0 rounded-full border-border/80 bg-background text-[10px] font-medium"
              >
                {meta.label}
              </Badge>
            </header>
            <div className="bg-background/90 px-4 py-4">
              <ArtifactBody artifact={a} />
            </div>
            {(a.export_key || a.schedule_key) && (
              <footer className="flex flex-wrap gap-2 border-t border-border/70 bg-background/70 px-4 py-2.5">
                {a.export_key ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-8 rounded-full"
                    disabled={busy !== null}
                    onClick={() => void onExport(a)}
                  >
                    <Download className="size-3.5" />
                    Export
                  </Button>
                ) : null}
                {a.schedule_key ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    className="h-8 rounded-full"
                    disabled={busy !== null}
                    onClick={() => void onSchedule(a)}
                  >
                    <CalendarClock className="size-3.5" />
                    Schedule
                  </Button>
                ) : null}
              </footer>
            )}
          </article>
        );
      })}
    </div>
  );
}
