"use client";
import { Suspense, type ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Clock3,
  CircleAlert,
} from "lucide-react";
import { usePeriod } from "@/components/AppShell";
import { AskCopilotButton } from "@/components/chat/ask-copilot-button";
import { SelectableSurface } from "@/components/chat/ui-selection";
import { Card, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fmt, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Approval, KpiCatalog, Scorecard, Status } from "@/lib/types";

type PulseCell = {
  key: string;
  label: string;
  value: number;
  unit?: string;
  delta_pct?: number | null;
  delta_direction?: string;
  note?: string;
  tone?: string;
};

type TopIssue = {
  rank: number;
  title: string;
  summary?: string;
  severity: string;
  priority_label?: string;
  tags?: string[];
  flagged_by?: string[];
  recommendation?: string;
  action_key?: string;
  company_code?: string;
  company_codes?: string[];
};

type DraftAction = {
  key: string;
  title?: string;
  sla?: string;
  recipients?: { email: string; role_hint?: string }[];
  routes_to?: string[];
};

type Brief = {
  id: number;
  title: string;
  body: string;
  kind: string;
  period_date?: string;
  created_at?: string;
};

function coveragePct(coverage: number) {
  return Math.round(coverage * 100);
}

function formatPeriodLabel(period: string) {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

function briefDateLabel(brief: Brief | null | undefined) {
  const raw =
    brief?.period_date ||
    brief?.title?.match(/(\d{4}-\d{2}-\d{2})/)?.[1] ||
    brief?.created_at?.slice(0, 10);
  if (!raw) return null;
  const d = new Date(`${raw.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function MetricCard({
  eyebrow,
  value,
  children,
  selection,
}: {
  eyebrow: string;
  value: ReactNode;
  children?: ReactNode;
  selection?: Parameters<typeof SelectableSurface>[0]["selection"];
}) {
  const body = (
    <div className="flex h-full min-w-0 flex-col gap-3 rounded-[1.25rem] bg-card px-5 py-5 shadow-md ring-1 ring-black/[0.04]">
      <div className="text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
        {eyebrow}
      </div>
      <div className="text-4xl font-semibold tracking-tight tabular-nums">
        {value}
      </div>
      {children}
    </div>
  );
  if (!selection) return body;
  return (
    <SelectableSurface selection={selection} className="min-w-0">
      {body}
    </SelectableSurface>
  );
}

function EndOfDayBrief({
  brief,
  pending,
  freshness,
  pulseLoaded,
}: {
  brief: Brief | null | undefined;
  pending: Approval[];
  freshness: Scorecard["freshness"] | undefined;
  pulseLoaded: boolean;
}) {
  const completed: string[] = [];
  if (brief) {
    completed.push(
      brief.kind === "end_of_day_digest"
        ? "End-of-day brief generated"
        : "Morning brief generated",
    );
  }
  if (pulseLoaded) completed.push("Workforce pulse evaluated");
  if (freshness) completed.push("Scheduled KPI watches checked");
  if (completed.length === 0) {
    completed.push("Waiting for today’s briefing cycle");
  }

  const pendingItems =
    pending.length > 0
      ? pending.slice(0, 4).map((a) => a.context?.title || a.summary)
      : ["No pending decisions"];

  const followUps: string[] = [];
  const never = freshness?.counts.never ?? 0;
  const stale = freshness?.counts.stale ?? 0;
  if (never > 0) followUps.push("Investigate missing KPI submissions");
  if (stale > 0) followUps.push("Review failed source connections");
  if (followUps.length === 0) {
    followUps.push("Confirm scorecard coverage for the next period");
  }

  const dateLabel = briefDateLabel(brief);

  return (
    <Card
      title="End of Day Brief"
      action={
        <div className="flex flex-wrap items-center gap-2.5">
          {dateLabel ? (
            <span className="text-sm text-muted-foreground">{dateLabel}</span>
          ) : null}
          <Button
            size="sm"
            variant="outline"
            className="h-8 rounded-full px-3.5"
            render={<Link href="/actions" />}
            nativeButton={false}
          >
            View Full Brief
          </Button>
        </div>
      }
    >
      <div className="grid gap-4 rounded-[1.15rem] bg-muted/55 p-3.5 sm:p-4 lg:grid-cols-3">
        <BriefColumn
          icon={<CheckCircle2 className="size-4 text-[color:var(--success)]" />}
          title="Completed Today"
          tone="ok"
          items={completed}
        />
        <BriefColumn
          icon={
            <span className="inline-flex size-5 items-center justify-center rounded-full bg-warning/15 text-[11px] font-semibold text-warning">
              {pending.length || "·"}
            </span>
          }
          title="Pending Decisions"
          tone="attention"
          items={pendingItems}
        />
        <BriefColumn
          icon={<Clock3 className="size-4 text-muted-foreground" />}
          title="Tomorrow’s Follow-ups"
          tone="muted"
          items={followUps}
        />
      </div>
    </Card>
  );
}

function BriefColumn({
  icon,
  title,
  items,
  tone,
}: {
  icon: ReactNode;
  title: string;
  items: string[];
  tone: "ok" | "attention" | "muted";
}) {
  return (
    <section className="min-w-0 space-y-3">
      <div className="flex items-center gap-2">
        {icon}
        <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          {title}
        </h3>
      </div>
      <ul className="space-y-2">
        {items.map((item) => (
          <li
            key={item}
            className={cn(
              "rounded-xl bg-card/80 px-3 py-2.5 text-sm leading-snug ring-1",
              tone === "ok" && "ring-[color:var(--success)]/15",
              tone === "attention" && "ring-warning/20",
              tone === "muted" && "ring-border/70",
            )}
          >
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

const OWNER_SHORT: Record<string, string> = {
  "Group HR Operations": "Group HR",
  HRBPs: "HRBP",
  "BU heads": "BU head",
  "Talent Acquisition & Quality-of-Hire": "Talent Acquisition",
  "Future Skills": "Future Skills",
  "Capability & Learning": "L&D",
  "Workforce Strategy": "Workforce",
  "Internal Mobility & Succession": "Succession",
  "Employee Experience & Retention": "EX / Retention",
};

function shortenOwner(raw: string) {
  const mapped = OWNER_SHORT[raw];
  if (mapped) return mapped;
  if (raw.length <= 18) return raw;
  const head = raw.split(/\s*[&/·|,]\s*/)[0]?.trim() || raw;
  if (head.length <= 20) return head;
  return `${head.slice(0, 17).trimEnd()}…`;
}

function ownerForIssue(issue: TopIssue, drafts: DraftAction[]) {
  const draft = drafts.find((d) => d.key === issue.action_key);
  const route = draft?.routes_to?.find((r) => r === "L&D" || r === "HRBPs" || r === "HRBP");
  if (route) return shortenOwner(route);
  const hint = draft?.recipients?.[0]?.role_hint;
  if (hint) return shortenOwner(hint);
  if (draft?.routes_to?.[0]) return shortenOwner(draft.routes_to[0]);
  if (issue.flagged_by?.[0]) return shortenOwner(issue.flagged_by[0]);
  return "IC HR Lead";
}

function dueForIssue(issue: TopIssue, drafts: DraftAction[], period: string) {
  const draft = drafts.find((d) => d.key === issue.action_key);
  if (draft?.sla) {
    if (/due in (\d+)\s*day/i.test(draft.sla)) {
      const days = Number(draft.sla.match(/due in (\d+)/i)?.[1] || 0);
      const base = new Date(`${period}-15T12:00:00`);
      base.setDate(base.getDate() + days);
      return base.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });
    }
    if (/decide this week/i.test(draft.sla)) return "This week";
    if (/30-day/i.test(draft.sla)) return "30 days";
    return draft.sla;
  }
  return "—";
}

function issueSubtitle(issue: TopIssue) {
  if (issue.priority_label) return issue.priority_label;
  if (issue.tags?.[0]) return issue.tags[0];
  const codes =
    issue.company_codes ??
    (issue.company_code ? [issue.company_code] : []);
  if (codes.length) return codes.join(" · ");
  return null;
}

function shortAction(issue: TopIssue, drafts: DraftAction[]) {
  const draft = drafts.find((d) => d.key === issue.action_key);
  if (draft?.title) return draft.title;
  const raw = (issue.recommendation || issue.summary || "—").replace(/\s+/g, " ").trim();
  const first = raw.split(/(?<=[.!?])\s+/)[0]?.trim() || raw;
  return first.length > 96 ? `${first.slice(0, 93).trimEnd()}…` : first;
}

function trendMonths(period: string, count = 6) {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return [];
  const end = new Date(y, m - 1, 1);
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(end.getFullYear(), end.getMonth() - (count - 1 - i), 1);
    return {
      key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      label: d.toLocaleDateString(undefined, { month: "short" }),
      full: d.toLocaleDateString(undefined, { month: "long" }),
    };
  });
}

function ScoreTrend({
  score,
  period,
  coverage,
  provisional,
}: {
  score: number | null;
  period: string;
  coverage: number | null;
  provisional: boolean;
}) {
  const months = trendMonths(period, 6);
  const yTicks = [100, 90, 80, 70];
  const yMin = 70;
  const yMax = 100;
  const plot = { left: 36, right: 16, top: 28, bottom: 28, width: 320, height: 200 };
  const innerW = plot.width - plot.left - plot.right;
  const innerH = plot.height - plot.top - plot.bottom;
  const xAt = (i: number) =>
    plot.left + (months.length <= 1 ? innerW / 2 : (i / (months.length - 1)) * innerW);
  const yAt = (value: number) =>
    plot.top + ((yMax - value) / (yMax - yMin)) * innerH;
  const pointIndex = months.length - 1;
  const pointX = xAt(pointIndex);
  const clamped =
    score == null ? null : Math.min(yMax, Math.max(yMin, score));
  const pointY = clamped == null ? null : yAt(clamped);
  const monthFull = months[pointIndex]?.full ?? formatPeriodLabel(period);

  return (
    <div className="flex h-full min-h-[18rem] flex-col gap-4">
      <div className="relative min-h-[14.5rem] flex-1">
        <svg
          viewBox={`0 0 ${plot.width} ${plot.height}`}
          className="h-full w-full"
          role="img"
          aria-label="Group HR score trend chart"
        >
          {yTicks.map((tick) => {
            const y = yAt(tick);
            return (
              <g key={tick}>
                <line
                  x1={plot.left}
                  x2={plot.width - plot.right}
                  y1={y}
                  y2={y}
                  stroke="currentColor"
                  className="text-border/70"
                  strokeWidth="1"
                />
                <text
                  x={plot.left - 10}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-muted-foreground text-[10px]"
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {months.map((month, i) => (
            <text
              key={month.key}
              x={xAt(i)}
              y={plot.height - 6}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {month.label}
            </text>
          ))}

          {score != null && pointY != null && (
            <>
              <line
                x1={pointX}
                x2={pointX}
                y1={pointY}
                y2={plot.height - plot.bottom}
                stroke="currentColor"
                className="text-primary"
                strokeWidth="1.5"
                strokeDasharray="4 4"
              />
              <circle cx={pointX} cy={pointY} r="5.5" className="fill-primary" />
              <text
                x={pointX}
                y={pointY - 12}
                textAnchor="middle"
                className="fill-primary text-[11px] font-semibold"
              >
                {fmt(score)}
                {provisional ? "*" : ""}
              </text>
            </>
          )}
        </svg>

        <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6">
          <div className="rounded-xl bg-[#eceff5]/95 px-4 py-2.5 text-center shadow-sm ring-1 ring-black/[0.04] backdrop-blur-[2px]">
            <div className="text-[13px] font-semibold tracking-tight text-foreground/85">
              Historical scores not verified
            </div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              Add monthly snapshots to enable trend
            </div>
          </div>
        </div>
      </div>

      {provisional ? (
        <div className="rounded-xl bg-[#f8f0df] px-3.5 py-2.5 text-[12px] leading-snug text-[#8a6a2f]">
          * {monthFull} score provisional
          {coverage != null ? `; ${coverage}% weighted data coverage.` : "."}
        </div>
      ) : null}
    </div>
  );
}

function Dashboard() {
  const params = useSearchParams();
  const [storedPeriod, setPeriod] = usePeriod();
  const period = params.get("period") ?? storedPeriod;
  const { data, error, loading } = useApi<Scorecard>(
    `/scorecard?period=${period}`,
  );
  const pulse = useApi<{
    cells?: PulseCell[];
    insights?: string[];
    top_issues?: TopIssue[];
    scorecard_exception?: {
      title?: string;
      score?: number;
      status?: string;
      detail?: string;
    };
  }>("/workforce/pulse");
  const brief = useApi<{ brief: Brief | null }>("/briefs/latest");
  const approvals = useApi<Approval[]>("/approvals?status=pending");
  const actions = useApi<{ drafts?: DraftAction[] }>("/workforce/actions");
  const catalog = useApi<KpiCatalog>("/kpis");

  const pendingList = approvals.data ?? [];
  const drafts = actions.data?.drafts ?? [];
  const pillarWeights = catalog.data?.pillar_weights ?? {};
  const companies = data?.companies ?? [];
  const attention = companies.filter(
    (c) => c.status === "amber" || c.status === "red",
  );
  const redCount = companies.filter((c) => c.status === "red").length;
  const amberCount = companies.filter((c) => c.status === "amber").length;
  const greenCount = companies.filter((c) => c.status === "green").length;
  const coverage = data ? coveragePct(data.group.pillar_coverage) : null;
  const provisional = data ? data.group.pillar_coverage < 1 : false;
  const topIssues = (pulse.data?.top_issues ?? []).slice(0, 3);
  const pillars = data?.group.pillars ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Executive Overview"
        subtitle="Workforce performance, end-of-day decisions, and next actions."
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
            <div className="flex items-center gap-2 rounded-full bg-accent px-3 py-1.5 text-sm text-muted-foreground">
              Group: All ICs
            </div>
            {data?.synthetic_data ? (
              <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(15,98,77,0.12)] px-3 py-1.5 text-xs font-medium text-[#0F624D]">
                <span className="size-1.5 rounded-full bg-[#0F624D]" />
                Demo · sample data
              </div>
            ) : null}
          </>
        }
      />

      <Loading error={error} loading={loading && !data} />

      {data && (
        <div className="grid gap-3 md:grid-cols-3">
          <MetricCard
            eyebrow="Group HR Score"
            value={
              <div className="flex flex-wrap items-center gap-2.5">
                <span>{fmt(data.group.score)}</span>
                {provisional ? (
                  <span className="rounded-md bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning">
                    Provisional
                  </span>
                ) : null}
              </div>
            }
            selection={{
              type: "group_score_tile",
              id: "scorecard.group",
              label: "Group HR Score",
              route: `/home?period=${period}`,
              period,
              dataSnapshot: {
                score: data.group.score,
                status: data.group.status,
                pillar_coverage: data.group.pillar_coverage,
              },
            }}
          >
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <StatusBadge
                status={data.group.status}
                withheld={data.group.status_withheld}
              />
              <span className="text-muted-foreground">
                {provisional
                  ? "Scored on partial data."
                  : `${data.group.companies_with_data}/${data.group.companies_in_scope} ICs with data`}
              </span>
            </div>
          </MetricCard>

          <MetricCard
            eyebrow="Weighted KPI Coverage"
            value={`${coverage ?? "—"}%`}
            selection={{
              type: "group_score_tile",
              id: "scorecard.coverage",
              label: "Weighted KPI Coverage",
              route: `/home?period=${period}`,
              period,
              dataSnapshot: { pillar_coverage: data.group.pillar_coverage },
            }}
          >
            <div className="space-y-2">
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${coverage ?? 0}%` }}
                />
              </div>
              <p className="text-sm text-muted-foreground">
                {provisional
                  ? "Several pillars have no current data."
                  : "Full weighted coverage for this period."}
              </p>
            </div>
          </MetricCard>

          <MetricCard
            eyebrow="ICs Requiring Attention"
            value={`${attention.length} of ${companies.length || data.group.companies_in_scope}`}
            selection={{
              type: "group_score_tile",
              id: "scorecard.attention",
              label: "ICs Requiring Attention",
              route: `/company?period=${period}`,
              period,
              dataSnapshot: {
                red: redCount,
                amber: amberCount,
                green: greenCount,
              },
            }}
          >
            <p className="text-sm text-muted-foreground">
              {redCount} off track · {amberCount} need attention · {greenCount}{" "}
              on track
            </p>
          </MetricCard>
        </div>
      )}

      <EndOfDayBrief
        brief={brief.data?.brief}
        pending={pendingList}
        freshness={data?.freshness}
        pulseLoaded={!!pulse.data}
      />

      <Card contentClassName="pt-0">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0 space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">
              Top Priorities → Recommended Actions
            </h2>
            <p className="max-w-2xl text-sm text-muted-foreground">
              One priority connects to one proposed action. Review and approve
              only in Decisions &amp; Actions.
            </p>
          </div>
          <Link
            href="/actions"
            className="shrink-0 text-sm font-medium text-primary hover:underline"
          >
            Open Actions →
          </Link>
        </div>

        {topIssues.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No priority actions for this period.
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl ring-1 ring-border/70">
            <Table className="table-fixed">
              <TableHeader>
                <TableRow className="border-b border-border/70 bg-muted/50 hover:bg-muted/50">
                  <TableHead className="w-12 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    #
                  </TableHead>
                  <TableHead className="w-[28%] text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    HR Risk / Priority
                  </TableHead>
                  <TableHead className="text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    Recommended next action
                  </TableHead>
                  <TableHead className="w-[7.5rem] text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    Owner
                  </TableHead>
                  <TableHead className="w-[5rem] text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
                    Due
                  </TableHead>
                  <TableHead className="w-[4.25rem]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {topIssues.map((issue, index) => {
                  const subtitle = issueSubtitle(issue);
                  const owner = ownerForIssue(issue, drafts);
                  const due = dueForIssue(issue, drafts, period);
                  return (
                    <SelectableSurface
                      as="tr"
                      key={issue.rank}
                      selection={{
                        type: "top_issue",
                        id: `issue.${issue.rank}`,
                        label: issue.title,
                        route: `/actions`,
                        period,
                        refs: { issue_rank: issue.rank },
                        dataSnapshot: { ...issue },
                      }}
                      className="border-b border-border/60 last:border-b-0 transition-colors hover:bg-muted/30 data-[selected=true]:bg-primary/5"
                    >
                      <TableCell className="align-middle">
                        <span className="inline-flex size-7 items-center justify-center rounded-md bg-primary/12 text-xs font-semibold text-primary">
                          {index + 1}
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[16rem] whitespace-normal align-middle">
                        <div className="min-w-0 space-y-0.5">
                          <div className="line-clamp-2 font-semibold tracking-tight">
                            {issue.title}
                          </div>
                          {subtitle ? (
                            <div className="line-clamp-1 text-xs text-muted-foreground">
                              {subtitle}
                            </div>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="max-w-md min-w-0 whitespace-normal align-middle text-sm text-foreground/80">
                        <span className="line-clamp-2 break-words">
                          {shortAction(issue, drafts)}
                        </span>
                      </TableCell>
                      <TableCell className="min-w-0 whitespace-normal align-middle text-sm">
                        <span className="line-clamp-2 break-words" title={owner}>
                          {owner}
                        </span>
                      </TableCell>
                      <TableCell className="min-w-0 overflow-hidden align-middle text-sm">
                        <span className="block truncate" title={due}>
                          {due}
                        </span>
                      </TableCell>
                      <TableCell className="align-middle text-right">
                        <Link
                          href="/actions"
                          className="text-sm font-semibold tracking-tight whitespace-nowrap hover:text-primary"
                          onClick={(e) => e.stopPropagation()}
                        >
                          View →
                        </Link>
                      </TableCell>
                    </SelectableSurface>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      {data && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <Card title="Group HR Pillar Performance">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pillar</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead className="text-right">Wt</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pillars.map((p) => (
                    <SelectableSurface
                      as="tr"
                      key={p.pillar}
                      selection={{
                        type: "pillar_tile",
                        id: `pillar.${p.pillar}`,
                        label: label(p.pillar),
                        route: `/company?tab=pillars&pillar=${p.pillar}`,
                        period,
                        refs: { pillar: p.pillar },
                        dataSnapshot: {
                          pillar: p.pillar,
                          score: p.score,
                          status: p.status,
                          eligible_weight: p.eligible_weight,
                        },
                      }}
                      className="border-b transition-colors hover:bg-muted/40 data-[selected=true]:bg-primary/5"
                    >
                      <TableCell className="font-medium">
                        <Link
                          href={`/company?tab=pillars&pillar=${p.pillar}`}
                          className="hover:text-primary hover:underline"
                        >
                          {label(p.pillar)}
                        </Link>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(p.score)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {Math.round((pillarWeights[p.pillar] ?? 0) * 100)}%
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={p.status as Status} />
                      </TableCell>
                    </SelectableSurface>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>

          <Card
            title="Group HR Score Trend"
            className="h-full"
            action={
              <Select defaultValue="12">
                <SelectTrigger
                  size="sm"
                  className="h-8 gap-1 rounded-lg border-border/80 bg-card px-2.5 text-xs font-medium text-foreground shadow-none"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="end">
                  <SelectItem value="6">6 months</SelectItem>
                  <SelectItem value="12">12 months</SelectItem>
                </SelectContent>
              </Select>
            }
            contentClassName="flex min-h-0 flex-1 flex-col pt-1"
          >
            <ScoreTrend
              score={data.group.score}
              period={period}
              coverage={coverage}
              provisional={provisional}
            />
          </Card>
        </div>
      )}

      {pulse.data?.cells && pulse.data.cells.length > 0 ? (
        <Card title="Workforce Pulse">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(10.5rem,1fr))] gap-3 rounded-[1.35rem] bg-muted/70 p-3">
            {pulse.data.cells.map((c) => {
              const alert =
                c.tone === "alert" || c.delta_direction === "down";
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
          {pulse.data.scorecard_exception ? (
            <div className="mt-4 flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-destructive/25 bg-destructive/[0.06] px-4 py-3.5">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 text-sm font-semibold text-destructive">
                  <CircleAlert className="size-4 shrink-0" />
                  {pulse.data.scorecard_exception.title ||
                    "Scorecard exception"}
                </div>
                {pulse.data.scorecard_exception.detail ? (
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {pulse.data.scorecard_exception.detail}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  className="rounded-full"
                  render={<Link href="/actions" />}
                  nativeButton={false}
                >
                  Review action
                  <ArrowRight className="size-3.5" />
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
            </div>
          ) : null}
        </Card>
      ) : null}
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
