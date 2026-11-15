"use client";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { BriefCard } from "@/components/BriefCard";
import { AskCopilotButton } from "@/components/chat/ask-copilot-button";
import { SelectableSurface } from "@/components/chat/ui-selection";
import type { ChatArtifact } from "@/components/chat/types";
import { WidgetBody } from "@/components/dashboard/widget-body";
import { Card, Loading, PageHeader, ScoreTile } from "@/components/ui";
import PinButton from "@/components/PinButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { download } from "@/lib/api";
import { label, PILLAR_SHORT } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Scorecard } from "@/lib/types";

type LayoutSection = { key: string; visible: boolean };
type LayoutWidget = {
  id: string;
  title: string;
  kind: string;
  artifact: ChatArtifact;
  source?: Record<string, unknown> | null;
};
type DashboardLayout = {
  sections: LayoutSection[];
  widgets: LayoutWidget[];
  pulse_cells?: {
    id: string;
    key: string;
    label: string;
    source: string;
    visible?: boolean;
  }[];
  pulse_hidden?: string[];
  updated_at?: string | null;
};

const DEFAULT_SECTIONS: LayoutSection[] = [
  { key: "brief", visible: true },
  { key: "pulse", visible: true },
  { key: "scorecard", visible: true },
  { key: "exception", visible: true },
  { key: "issues", visible: true },
  { key: "pinned_widgets", visible: true },
];

const LAYOUT_CHANGED = "dashboard-layout:changed";

function Dashboard() {
  const params = useSearchParams();
  const [storedPeriod, setPeriod] = usePeriod();
  const period = params.get("period") ?? storedPeriod; // a pinned view brings its own period
  const { data, error, loading } = useApi<Scorecard>(
    `/scorecard?period=${period}`,
  );
  const layoutApi = useApi<DashboardLayout>("/dashboard/layout");
  const pulse = useApi<{
    cells?: {
      key: string;
      label: string;
      value: number;
      unit?: string;
      delta_pct?: number | null;
      delta_direction?: string;
      note?: string;
      tone?: string;
    }[];
    insights?: string[];
    top_issues?: {
      rank: number;
      title: string;
      summary?: string;
      severity: string;
      priority_label?: string;
      tags?: string[];
      flagged_by?: string[];
      recommendation?: string;
    }[];
    scorecard_exception?: {
      title?: string;
      score?: number;
      status?: string;
      detail?: string;
    };
  }>("/workforce/pulse");
  const brief = useApi<{
    brief: { id: number; title: string; body: string; kind: string } | null;
  }>("/briefs/latest");
  const [exportError, setExportError] = useState<string | null>(null);
  const viewPath = `/home?${new URLSearchParams({ period })}`;

  useEffect(() => {
    const onChanged = () => {
      layoutApi.reload();
      pulse.reload();
    };
    window.addEventListener(LAYOUT_CHANGED, onChanged);
    return () => window.removeEventListener(LAYOUT_CHANGED, onChanged);
  }, [layoutApi.reload, pulse.reload]);

  const sections =
    layoutApi.data?.sections?.length ? layoutApi.data.sections : DEFAULT_SECTIONS;
  const widgets = layoutApi.data?.widgets ?? [];
  const visible = (key: string) =>
    sections.find((s) => s.key === key)?.visible !== false;

  const pulseBlock =
    visible("pulse") && pulse.data?.cells && pulse.data.cells.length > 0 ? (
      <Card title="Workforce pulse">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(10.5rem,1fr))] gap-3 rounded-[1.35rem] bg-muted/70 p-3">
          {pulse.data.cells.map((c) => {
            const alert = c.tone === "alert" || c.delta_direction === "down";
            const good = c.tone === "good" || c.delta_direction === "up";
            return (
              <SelectableSurface
                key={c.key}
                selection={{
                  type: "pulse_cell",
                  id: `pulse.${c.key}`,
                  label: c.label,
                  route: `/home?period=${period}`,
                  period,
                  refs: { pulse_key: c.key },
                  dataSnapshot: { ...c },
                }}
                className="min-w-0 rounded-2xl bg-card px-3.5 py-3.5 shadow-sm ring-1 ring-black/[0.03] transition-shadow hover:shadow-md"
              >
                <div
                  className="line-clamp-2 text-xs font-medium text-muted-foreground"
                  title={c.label}
                >
                  {c.label}
                </div>
                <div className="mt-1.5 flex items-baseline gap-1 text-2xl font-semibold tabular-nums tracking-tight">
                  {typeof c.value === "number"
                    ? c.value.toLocaleString()
                    : c.value}
                  {c.unit ? (
                    <span className="text-sm font-medium text-muted-foreground">
                      {c.unit}
                    </span>
                  ) : null}
                </div>
                {(c.note || c.delta_pct != null) && (
                  <div
                    className={cn(
                      "mt-1 text-[11px]",
                      alert
                        ? "text-destructive"
                        : good
                          ? "text-[color:var(--success)]"
                          : "text-muted-foreground",
                    )}
                  >
                    {c.delta_pct != null
                      ? `${c.delta_direction === "down" ? "▼" : c.delta_direction === "up" ? "▲" : "·"} ${Math.abs(c.delta_pct)}${c.key === "ex_index" ? "" : "%"}`
                      : ""}
                    {c.note ? ` ${c.note}` : ""}
                  </div>
                )}
              </SelectableSurface>
            );
          })}
        </div>

        {pulse.data.insights && pulse.data.insights.length > 0 && (
          <ul className="mt-4 space-y-1.5 text-sm text-muted-foreground">
            {pulse.data.insights.map((line) => (
              <li key={line} className="flex gap-2">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    ) : null;

  const scorecardTiles =
    visible("scorecard") && data ? (
      <div className="grid grid-cols-[repeat(auto-fit,minmax(10.5rem,1fr))] gap-3">
        <SelectableSurface
          className="min-w-0 sm:col-span-2"
          selection={{
            type: "group_score_tile",
            id: "scorecard.group",
            label: "Group score",
            route: `/home?period=${period}`,
            period,
            dataSnapshot: {
              score: data.group.score,
              status: data.group.status,
              pillar_coverage: data.group.pillar_coverage,
              companies_with_data: data.group.companies_with_data,
              companies_in_scope: data.group.companies_in_scope,
            },
          }}
        >
          <ScoreTile
            accent
            title="Group score"
            score={data.group.score}
            status={data.group.status}
            withheld={data.group.status_withheld}
            note={
              data.group.pillar_coverage < 1
                ? `Only ${Math.round(data.group.pillar_coverage * 100)}% of weight scored`
                : `${data.group.companies_with_data}/${data.group.companies_in_scope} companies with data`
            }
          />
        </SelectableSurface>
        {data.group.pillars.map((p) => (
          <SelectableSurface
            key={p.pillar}
            className="min-w-0"
            selection={{
              type: "pillar_tile",
              id: `pillar.${p.pillar}`,
              label: label(p.pillar),
              route: `/home?period=${period}`,
              period,
              refs: { pillar: p.pillar },
              dataSnapshot: {
                pillar: p.pillar,
                score: p.score,
                status: p.status,
                eligible_weight: p.eligible_weight,
              },
            }}
          >
            <ScoreTile
              title={label(p.pillar)}
              shortTitle={PILLAR_SHORT[p.pillar] ?? label(p.pillar)}
              score={p.score}
              status={p.status}
              href={`/company?tab=pillars&pillar=${p.pillar}`}
              note={
                p.eligible_weight < 1
                  ? `${Math.round(p.eligible_weight * 100)}% of KPIs scored`
                  : undefined
              }
            />
          </SelectableSurface>
        ))}
      </div>
    ) : null;

  const exceptionBlock =
    visible("exception") && pulse.data?.scorecard_exception ? (
      <SelectableSurface
        selection={{
          type: "scorecard_exception",
          id: "pulse.exception",
          label:
            pulse.data.scorecard_exception.title || "Scorecard exception",
          route: `/home?period=${period}`,
          period,
          dataSnapshot: { ...pulse.data.scorecard_exception },
        }}
        className="rounded-2xl border border-destructive/25 bg-destructive/[0.06] px-4 py-3.5"
      >
        <div className="text-sm font-semibold text-destructive">
          {pulse.data.scorecard_exception.title ||
            "Scorecard exception — Retention is off track"}
        </div>
        {pulse.data.scorecard_exception.detail ? (
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
            {pulse.data.scorecard_exception.detail}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            className="rounded-full"
            render={<Link href="/actions" />}
            nativeButton={false}
          >
            Approve &amp; execute corrective action
          </Button>
          <AskCopilotButton
            size="sm"
            variant="outline"
            className="rounded-full"
            selection={{
              type: "scorecard_exception",
              id: "pulse.exception",
              label:
                pulse.data.scorecard_exception.title ||
                "Scorecard exception",
              route: `/home?period=${period}`,
              period,
              dataSnapshot: { ...pulse.data.scorecard_exception },
            }}
          />
        </div>
      </SelectableSurface>
    ) : null;

  const issuesBlock =
    visible("issues") &&
    pulse.data?.top_issues &&
    pulse.data.top_issues.length > 0 ? (
      <div className="space-y-2.5">
        <h3 className="text-sm font-semibold tracking-tight">
          {pulse.data.top_issues.length} issues needing your attention
        </h3>
        <div className="max-h-[36rem] space-y-2.5 overflow-y-auto pr-1">
          {pulse.data.top_issues.map((issue) => {
            const high =
              issue.severity === "high" ||
              issue.severity === "urgent" ||
              issue.rank <= 2;
            return (
              <SelectableSurface
                key={issue.rank}
                selection={{
                  type: "top_issue",
                  id: `issue.${issue.rank}`,
                  label: issue.title,
                  route: `/home?period=${period}`,
                  period,
                  refs: { issue_rank: issue.rank },
                  dataSnapshot: { ...issue },
                }}
                className={cn(
                  "rounded-xl border border-border/70 bg-card py-3 pl-3 pr-4 shadow-sm",
                  "border-l-[3px]",
                  high ? "border-l-destructive" : "border-l-warning",
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
                      high
                        ? "bg-destructive/10 text-destructive"
                        : "bg-warning/15 text-warning",
                    )}
                  >
                    <span
                      className={cn(
                        "mr-1.5 inline-block size-1.5 rounded-full",
                        high ? "bg-destructive" : "bg-warning",
                      )}
                    />
                    {issue.priority_label || (high ? "High" : "Medium")}
                  </span>
                  <span className="text-[10px] tabular-nums text-muted-foreground">
                    #{issue.rank}
                  </span>
                </div>
                <div className="mt-1.5 text-sm font-semibold leading-snug">
                  {issue.title}
                </div>
                {issue.summary ? (
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {issue.summary}
                  </p>
                ) : null}
                {issue.tags && issue.tags.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {issue.tags.map((t) => (
                      <span
                        key={t}
                        className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                ) : null}
                {issue.recommendation ? (
                  <p className="mt-2 text-xs leading-relaxed">
                    <span className="font-semibold">Recommended path: </span>
                    {issue.recommendation}
                  </p>
                ) : null}
                {issue.flagged_by && issue.flagged_by.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {issue.flagged_by.map((f) => (
                      <span
                        key={f}
                        className="inline-flex items-center rounded-full bg-[rgba(15,98,77,0.12)] px-2 py-0.5 text-[10px] font-medium text-[#0F624D]"
                      >
                        {f}
                      </span>
                    ))}
                  </div>
                ) : null}
              </SelectableSurface>
            );
          })}
        </div>
      </div>
    ) : visible("issues") &&
      !pulse.data?.scorecard_exception &&
      data &&
      !(pulse.data?.top_issues && pulse.data.top_issues.length > 0) ? (
      <p className="text-sm text-muted-foreground">
        No priority actions for this period.
      </p>
    ) : null;

  const pinnedBlock =
    visible("pinned_widgets") && widgets.length > 0 ? (
      <Card title="Pinned widgets">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(16rem,1fr))] gap-3">
          {widgets.map((w) => {
            const artifact: ChatArtifact = {
              ...(w.artifact || {}),
              kind: w.kind || w.artifact?.kind || "table",
              title: w.title || w.artifact?.title,
            };
            return (
              <div
                key={w.id}
                className="min-w-0 overflow-hidden rounded-2xl border border-border/80 bg-background/90 shadow-sm"
              >
                <div className="border-b border-border/70 px-3 py-2 text-sm font-semibold tracking-tight">
                  {artifact.title || w.kind}
                </div>
                <div className="px-3 py-3">
                  <WidgetBody artifact={artifact} />
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    ) : null;

  const scorecardBundle =
    scorecardTiles || exceptionBlock || issuesBlock ? (
      <Card
        title="Scorecard & actions"
        action={
          <div className="flex items-center gap-3 text-sm">
            <Link href="/actions" className="text-primary hover:underline">
              Review draft actions
            </Link>
            <AskCopilotButton
              variant="link"
              size="sm"
              className="h-auto px-0 text-muted-foreground"
            />
          </div>
        }
      >
        <div className="space-y-5">
          {scorecardTiles}
          {(exceptionBlock || issuesBlock) && (
            <div className="min-w-0 space-y-3">
              {exceptionBlock}
              {issuesBlock}
            </div>
          )}
        </div>
      </Card>
    ) : null;

  /** Render independent sections in stored order; scorecard/exception/issues share one card when adjacent. */
  const rendered: ReactNode[] = [];
  let scorecardEmitted = false;
  for (const section of sections) {
    if (!section.visible) continue;
    if (section.key === "brief" && brief.data?.brief) {
      rendered.push(<BriefCard key="brief" brief={brief.data.brief} />);
      continue;
    }
    if (section.key === "pulse" && pulseBlock) {
      rendered.push(<div key="pulse">{pulseBlock}</div>);
      continue;
    }
    if (
      (section.key === "scorecard" ||
        section.key === "exception" ||
        section.key === "issues") &&
      !scorecardEmitted &&
      scorecardBundle
    ) {
      rendered.push(<div key="scorecard-bundle">{scorecardBundle}</div>);
      scorecardEmitted = true;
      continue;
    }
    if (section.key === "pinned_widgets" && pinnedBlock) {
      rendered.push(<div key="pinned">{pinnedBlock}</div>);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Home"
        subtitle="Group overview across companies and pillars for the selected period."
        actions={
          <>
            <div className="flex items-center gap-2.5 rounded-full bg-accent px-3 py-1.5 text-sm">
              <Label htmlFor="period" className="text-muted-foreground">
                Period
              </Label>
              <Input
                id="period"
                type="month"
                value={period}
                onChange={(e) => e.target.value && setPeriod(e.target.value)}
                className="h-9 w-auto rounded-full border-transparent bg-white px-3 shadow-xs"
              />
            </div>
            <PinButton
              kind="view"
              target={viewPath}
              label={`Dashboard ${period}`}
            />
            {(["xlsx", "csv"] as const).map((f) => (
              <Button
                key={f}
                variant={f === "xlsx" ? "default" : "outline"}
                className="h-10 rounded-full px-4"
                onClick={() =>
                  download(
                    `/reports/export/scorecard.${f}?period=${period}`,
                    `group-overview-${period}.${f}`,
                  )
                    .then(() => setExportError(null))
                    .catch((e) => setExportError(e.message))
                }
              >
                Export {f === "xlsx" ? "Excel" : "CSV"}
              </Button>
            ))}
          </>
        }
      />
      <Loading error={error} loading={loading} />
      {exportError && (
        <Alert variant="destructive">
          <AlertDescription>{exportError}</AlertDescription>
        </Alert>
      )}
      {rendered}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <Dashboard />
    </Suspense>
  );
}
