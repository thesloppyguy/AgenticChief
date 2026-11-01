"use client";
import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Donut } from "@/components/charts";
import { Card, Loading, PageHeader, ScoreTile, StatusBadge } from "@/components/ui";
import PinButton from "@/components/PinButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { FreshnessLine } from "@/components/FreshnessLine";
import { download } from "@/lib/api";
import { fmt, label, PILLAR_SHORT, STATUS_STYLE } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Scorecard } from "@/lib/types";

type StatusFilter = "all" | "green" | "amber" | "red" | "none";

const FILTER_ITEMS = [
  { value: "all", label: "All" },
  { value: "red", label: "Off track" },
  { value: "amber", label: "Needs attention" },
  { value: "green", label: "On track" },
  { value: "none", label: "No data" },
];

function Dashboard() {
  const params = useSearchParams();
  const [storedPeriod, setPeriod] = usePeriod();
  const period = params.get("period") ?? storedPeriod; // a pinned view brings its own period
  const { data, error, loading } = useApi<Scorecard>(
    `/scorecard?period=${period}`,
  );
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
    artifact?: {
      issues?: {
        rank?: number;
        title?: string;
        summary?: string;
        severity?: string;
        priority_label?: string;
        tags?: string[];
        flagged_by?: string[];
        recommendation?: string;
      }[];
      insights?: string[];
      exceptions?: {
        title?: string;
        score?: number | null;
        detail?: string;
      }[];
    };
  }>("/workforce/pulse");
  const brief = useApi<{
    brief: { id: number; title: string; body: string; kind: string } | null;
  }>("/briefs/latest");
  const [q, setQ] = useState(params.get("q") ?? "");
  const [filter, setFilter] = useState<StatusFilter>(
    (params.get("status") as StatusFilter) ?? "all",
  );
  const [exportError, setExportError] = useState<string | null>(null);
  const viewPath = `/?${new URLSearchParams({ period, ...(filter !== "all" ? { status: filter } : {}), ...(q ? { q } : {}) })}`;
  const [asc, setAsc] = useState(true);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.companies
      .filter((c) => (c.code + c.name).toLowerCase().includes(q.toLowerCase()))
      .filter(
        (c) =>
          filter === "all" ||
          (filter === "none" ? c.status == null : c.status === filter),
      )
      .sort((a, b) => {
        if (a.score == null) return 1;
        if (b.score == null) return -1;
        return asc ? a.score - b.score : b.score - a.score;
      });
  }, [data, q, filter, asc]);

  const dist = useMemo(() => {
    const d = { green: 0, amber: 0, red: 0, none: 0 };
    data?.companies.forEach((c) => {
      d[c.status ?? "none"]++;
    });
    return d;
  }, [data]);
  const lowCoverage =
    data?.companies.filter((c) => c.pillar_coverage < 1).length ?? 0;

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
              label={`Dashboard ${period}${filter !== "all" ? ` · ${filter}` : ""}${q ? ` · “${q}”` : ""}`}
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
      {data?.freshness && (
        <FreshnessLine freshness={data.freshness} />
      )}
      <Loading error={error} loading={loading} />
      {brief.data?.brief && (
        <Card title={brief.data.brief.title}>
          <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap text-sm text-muted-foreground">
            {brief.data.brief.body}
          </pre>
        </Card>
      )}
      {pulse.data?.cells && pulse.data.cells.length > 0 && (
        <Card title="Workforce pulse">
          <div className="grid gap-3 rounded-[1.35rem] bg-muted/70 p-3 sm:grid-cols-2 lg:grid-cols-5">
            {pulse.data.cells.map((c) => {
              const alert = c.tone === "alert" || c.delta_direction === "down";
              const good = c.tone === "good" || c.delta_direction === "up";
              return (
                <div
                  key={c.key}
                  className="rounded-2xl bg-card px-3.5 py-3.5 shadow-sm ring-1 ring-black/[0.03] transition-shadow hover:shadow-md"
                >
                  <div className="text-xs font-medium text-muted-foreground">{c.label}</div>
                  <div className="mt-1.5 flex items-baseline gap-1 text-2xl font-semibold tabular-nums tracking-tight">
                    {typeof c.value === "number" ? c.value.toLocaleString() : c.value}
                    {c.unit ? (
                      <span className="text-sm font-medium text-muted-foreground">{c.unit}</span>
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
                </div>
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
      )}
      {exportError && (
        <Alert variant="destructive">
          <AlertDescription>{exportError}</AlertDescription>
        </Alert>
      )}
      {(data ||
        pulse.data?.scorecard_exception ||
        (pulse.data?.top_issues && pulse.data.top_issues.length > 0)) && (
        <Card
          title="Scorecard & actions"
          action={
            <div className="flex gap-3 text-sm">
              <Link href="/actions" className="text-primary hover:underline">
                Review draft actions
              </Link>
              <Link href="/chat" className="text-muted-foreground hover:underline">
                Ask the Co-Pilot
              </Link>
            </div>
          }
        >
          <div className="grid items-start gap-5 lg:grid-cols-12">
            {data && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:col-span-5 lg:grid-cols-2">
                <div className="col-span-2 sm:col-span-3 lg:col-span-2">
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
                </div>
                {data.group.pillars.map((p) => (
                  <ScoreTile
                    key={p.pillar}
                    title={label(p.pillar)}
                    score={p.score}
                    status={p.status}
                    href={`/company?tab=pillars&pillar=${p.pillar}`}
                    note={
                      p.eligible_weight < 1
                        ? `${Math.round(p.eligible_weight * 100)}% of KPIs scored`
                        : undefined
                    }
                  />
                ))}
              </div>
            )}

            <div
              className={cn(
                "min-w-0 space-y-3",
                data ? "lg:col-span-7" : "lg:col-span-12",
              )}
            >
              {pulse.data?.scorecard_exception && (
                <div className="rounded-2xl border border-destructive/25 bg-destructive/[0.06] px-4 py-3.5">
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
                    <Button
                      size="sm"
                      variant="outline"
                      className="rounded-full"
                      render={<Link href="/chat" />}
                      nativeButton={false}
                    >
                      Ask the Co-Pilot
                    </Button>
                  </div>
                </div>
              )}

              {pulse.data?.top_issues && pulse.data.top_issues.length > 0 ? (
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
                        <div
                          key={issue.rank}
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
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                !pulse.data?.scorecard_exception && data && (
                  <p className="text-sm text-muted-foreground">
                    No priority actions for this period.
                  </p>
                )
              )}
            </div>
          </div>
        </Card>
      )}
      {data && (
        <>
          <div className="grid items-start gap-5 lg:grid-cols-12">
            <div className="min-w-0 lg:col-span-8">
              <Card
                title={`Companies (${rows.length})`}
                contentClassName="[&_[data-slot=table-container]]:max-h-[34rem] [&_[data-slot=table-container]]:overflow-y-auto [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-muted"
                action={
                  <div className="flex gap-2.5 text-base">
                    <Input
                      aria-label="Search companies"
                      placeholder="Search…"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                      className="h-11 w-auto px-3 text-base md:text-base"
                    />
                    <Select
                      items={FILTER_ITEMS}
                      value={filter}
                      onValueChange={(v) =>
                        v != null && setFilter(v as StatusFilter)
                      }
                    >
                      <SelectTrigger
                        aria-label="Filter by status"
                        className="h-11 px-3 text-base data-[size=default]:h-11"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {FILTER_ITEMS.map((i) => (
                          <SelectItem key={i.value} value={i.value}>
                            {i.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                }
              >
                <Table className="text-base">
                  <TableHeader>
                    <TableRow>
                      <TableHead className="h-11 text-sm">Company</TableHead>
                      <TableHead
                        aria-sort={asc ? "ascending" : "descending"}
                        className="h-11 text-sm"
                      >
                        <Button
                          variant="link"
                          size="sm"
                          onClick={() => setAsc(!asc)}
                          className="h-auto px-0 text-sm decoration-dotted"
                        >
                          Overall {asc ? "▲" : "▼"}
                        </Button>
                      </TableHead>
                      <TableHead className="h-11 text-sm">Status</TableHead>
                      {data.group.pillars.map((p) => (
                        <TableHead
                          key={p.pillar}
                          title={label(p.pillar)}
                          className="h-11 px-1.5 text-center text-sm font-normal"
                        >
                          {PILLAR_SHORT[p.pillar] ?? label(p.pillar)}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((c) => (
                      <TableRow key={c.company_id}>
                        <TableCell className="py-3">
                          <Link
                            className="block max-w-[10rem] truncate hover:underline"
                            href={`/company?company=${c.company_id}`}
                          >
                            {c.code} · {c.name}
                          </Link>
                        </TableCell>
                        <TableCell className="py-3 tabular-nums">
                          {fmt(c.score)}
                        </TableCell>
                        <TableCell className="py-3">
                          <StatusBadge
                            status={c.status}
                            withheld={c.status_withheld}
                          />
                        </TableCell>
                        {c.pillars.map((p) => {
                          const s = p.status;
                          return (
                            <TableCell key={p.pillar} className="px-1.5 py-3 text-center">
                              <span
                                className={cn(
                                  "inline-block w-11 rounded-md border px-1.5 py-0.5 text-sm tabular-nums",
                                  s
                                    ? STATUS_STYLE[s]
                                    : "bg-muted text-muted-foreground",
                                )}
                              >
                                {fmt(p.score, 0)}
                              </span>
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </div>
            <div className="space-y-5 lg:col-span-4">
              <Card title="Companies by status">
                <div className="flex items-center gap-5">
                  <Donut
                    segments={[
                      { value: dist.green, color: "var(--success)", label: "On track" },
                      { value: dist.amber, color: "var(--warning)", label: "Needs attention" },
                      { value: dist.red, color: "var(--destructive)", label: "Off track" },
                      { value: dist.none, color: "var(--muted-foreground)", label: "No data" },
                    ]}
                    center={
                      <>
                        <div className="text-3xl font-semibold tabular-nums">{data.companies.length}</div>
                        <div className="text-sm text-muted-foreground">companies</div>
                      </>
                    }
                  />
                  <ul className="flex-1 space-y-2.5 text-base">
                    {[
                      ["On track", dist.green, "var(--success)"],
                      ["Needs attention", dist.amber, "var(--warning)"],
                      ["Off track", dist.red, "var(--destructive)"],
                      ["No data", dist.none, "var(--muted-foreground)"],
                    ].map(([name, n, color]) => (
                      <li key={name as string} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2.5">
                          <span className="size-3 rounded-full" style={{ background: color as string }} />
                          {name}
                        </span>
                        <span className="font-semibold tabular-nums">{n}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </Card>
              <Card title="Data quality">
                <p className="text-base text-muted-foreground">
                  {lowCoverage} of {data.companies.length} companies have at least
                  one pillar with no scoreable KPI. Missing or not-yet-due KPIs
                  are excluded and remaining weights rescaled — never treated as
                  zero.
                </p>
                {data.no_source_kpis.length > 0 && (
                  <p className="mt-3 text-base text-muted-foreground">
                    <strong>
                      {data.no_source_kpis.length} KPIs have no source
                    </strong>{" "}
                    ({data.no_source_kpis.map(label).join(", ")}). They are
                    excluded from every score until a source is connected.{" "}
                    <Link
                      href="/documents"
                      className="underline hover:text-foreground"
                    >
                      Knowledge
                    </Link>
                  </p>
                )}
              </Card>
            </div>
          </div>
        </>
      )}
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
