"use client";
import { Suspense, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { AskCopilotButton } from "@/components/chat/ask-copilot-button";
import { SelectableSurface } from "@/components/chat/ui-selection";
import { Card, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
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
import { fmt, label, reasonLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { CompanyCard, Scorecard, Status } from "@/lib/types";

interface CompanyDetail extends CompanyCard {
  company: { id: number; code: string; name: string };
  values: Record<
    string,
    {
      achievement: number | null;
      numerator: number | null;
      denominator: number | null;
    }
  >;
}

type KpiRow = {
  key: string;
  pillar: string;
  score: number | null;
  excluded_reason: string | null;
  achievement: number | null;
};

function coveragePct(coverage: number) {
  return Math.round(coverage * 100);
}

function formatPeriodLabel(period: string) {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "long",
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

function CompanyView() {
  const params = useSearchParams();
  const [storedPeriod, setPeriod] = usePeriod();
  const period = params.get("period") ?? storedPeriod;
  const card = useApi<Scorecard>(`/scorecard?period=${period}`);
  const companies = card.data?.companies ?? [];

  const preferred =
    params.get("company") != null
      ? Number(params.get("company"))
      : companies.find((c) => c.code === "LTF")?.company_id ??
        companies[0]?.company_id ??
        null;

  const [picked, setPicked] = useState<number | null>(
    params.get("company") ? Number(params.get("company")) : null,
  );
  const selectedId = picked ?? preferred;
  const selected =
    companies.find((c) => c.company_id === selectedId) ?? companies[0] ?? null;

  const detail = useApi<CompanyDetail>(
    selected ? `/scorecard/companies/${selected.company_id}?period=${period}` : null,
  );

  const [pillarFilter, setPillarFilter] = useState<string>(
    params.get("pillar") || "all",
  );
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const sortedCompanies = useMemo(
    () =>
      [...companies].sort((a, b) => {
        const as = a.score ?? Number.POSITIVE_INFINITY;
        const bs = b.score ?? Number.POSITIVE_INFINITY;
        return as - bs;
      }),
    [companies],
  );

  const kpiRows: KpiRow[] = useMemo(() => {
    if (!detail.data) return [];
    return detail.data.pillars.flatMap((p) =>
      p.kpis.map((k) => ({
        key: k.key,
        pillar: p.pillar,
        score: k.score,
        excluded_reason: k.excluded_reason,
        achievement: detail.data!.values[k.key]?.achievement ?? null,
      })),
    );
  }, [detail.data]);

  const filteredKpis = useMemo(() => {
    return kpiRows.filter((row) => {
      if (pillarFilter !== "all" && row.pillar !== pillarFilter) return false;
      if (statusFilter === "scored" && row.excluded_reason) return false;
      if (statusFilter === "missing" && !row.excluded_reason) return false;
      return true;
    });
  }, [kpiRows, pillarFilter, statusFilter]);

  const weakest = useMemo(() => {
    if (!detail.data) return null;
    const scored = detail.data.pillars
      .filter((p) => p.score != null)
      .sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
    return scored[0] ?? null;
  }, [detail.data]);

  const groupScore = card.data?.group.score ?? null;
  const icScore = selected?.score ?? null;
  const delta =
    groupScore != null && icScore != null
      ? Number((icScore - groupScore).toFixed(1))
      : null;
  const coverage = selected ? coveragePct(selected.pillar_coverage) : null;
  const provisional = selected ? selected.pillar_coverage < 1 : false;
  const missingPillars =
    detail.data?.pillars.filter((p) => p.score == null).length ?? 0;

  const selectCompany = (id: number) => {
    setPicked(id);
    setPillarFilter("all");
    setStatusFilter("all");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Group & IC Performance"
        subtitle="Compare Independent Companies and drill into HR pillar and KPI results."
        actions={
          <>
            <div className="flex items-center gap-2.5 rounded-full bg-accent px-3 py-1.5 text-sm">
              <Label htmlFor="company-period" className="text-muted-foreground">
                Period
              </Label>
              <Input
                id="company-period"
                type="month"
                value={period}
                onChange={(e) => e.target.value && setPeriod(e.target.value)}
                className="h-9 w-auto rounded-full border-transparent bg-white px-3 shadow-xs"
              />
            </div>
            <div className="flex items-center gap-2 rounded-full bg-accent px-3 py-1.5 text-sm text-muted-foreground">
              Group: All ICs
            </div>
            {card.data?.synthetic_data ? (
              <div className="inline-flex items-center gap-2 rounded-full bg-[rgba(15,98,77,0.12)] px-3 py-1.5 text-xs font-medium text-[#0F624D]">
                <span className="size-1.5 rounded-full bg-[#0F624D]" />
                Demo · sample data
              </div>
            ) : null}
          </>
        }
      />

      <Loading error={card.error} loading={card.loading && !card.data} />

      {selected && (
        <div className="grid gap-3 md:grid-cols-3">
          <MetricCard
            eyebrow={`Selected IC — ${selected.name}`}
            value={
              <div className="flex flex-wrap items-center gap-2.5">
                <span>{fmt(selected.score)}</span>
                <StatusBadge
                  status={selected.status}
                  withheld={selected.status_withheld}
                />
              </div>
            }
            selection={{
              type: "company_detail_header",
              id: `company.${selected.company_id}.header`,
              label: `${selected.code} · ${selected.name}`,
              route: `/company?company=${selected.company_id}`,
              period,
              refs: {
                company_id: selected.company_id,
                company_code: selected.code,
              },
              dataSnapshot: {
                score: selected.score,
                status: selected.status,
                pillar_coverage: selected.pillar_coverage,
              },
            }}
          >
            <p className="text-sm text-muted-foreground">
              Current IC HR score — {formatPeriodLabel(period)}
            </p>
          </MetricCard>

          <MetricCard
            eyebrow="Scorecard Coverage"
            value={`${coverage ?? "—"}%`}
            selection={{
              type: "company_detail_header",
              id: `company.${selected.company_id}.coverage`,
              label: `${selected.code} coverage`,
              route: `/company?company=${selected.company_id}`,
              period,
              refs: {
                company_id: selected.company_id,
                company_code: selected.code,
              },
              dataSnapshot: { pillar_coverage: selected.pillar_coverage },
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
                  ? "Provisional — many sub-KPIs unavailable."
                  : "Full weighted coverage for this IC."}
              </p>
            </div>
          </MetricCard>

          <MetricCard
            eyebrow="Group HR Score — Comparison"
            value={
              <div className="flex flex-wrap items-center gap-2.5">
                <span>{fmt(groupScore)}</span>
                {card.data && card.data.group.pillar_coverage < 1 ? (
                  <span className="rounded-md bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning">
                    Provisional
                  </span>
                ) : null}
              </div>
            }
            selection={{
              type: "group_score_tile",
              id: "scorecard.group.compare",
              label: "Group HR Score",
              route: `/company?company=${selected.company_id}`,
              period,
              dataSnapshot: {
                group_score: groupScore,
                ic_score: icScore,
                delta,
              },
            }}
          >
            <p className="text-sm text-muted-foreground">
              {delta == null
                ? "Waiting for both scores."
                : delta === 0
                  ? `${selected.code} matches the Group score.`
                  : `${selected.code} is ${Math.abs(delta)} points ${delta < 0 ? "below" : "above"} the Group score.`}
            </p>
          </MetricCard>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Compare Independent Companies">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Independent Company (IC)</TableHead>
                  <TableHead className="text-right">HR Score</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Select</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedCompanies.map((c) => {
                  const active = selected?.company_id === c.company_id;
                  return (
                    <TableRow
                      key={c.company_id}
                      className={cn(
                        active && "bg-primary/5",
                        "cursor-pointer",
                      )}
                      onClick={() => selectCompany(c.company_id)}
                    >
                      <TableCell className="font-medium">
                        <div className="flex flex-col">
                          <span>
                            {c.code}
                            {c.name && c.name !== c.code
                              ? ` — ${c.name}`
                              : ""}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(c.score)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          status={c.status}
                          withheld={c.status_withheld}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant={active ? "default" : "outline"}
                          className="h-8 rounded-full px-3"
                          onClick={(e) => {
                            e.stopPropagation();
                            selectCompany(c.company_id);
                          }}
                        >
                          {active ? "Selected" : "Select"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>

        <Card
          title={
            selected
              ? `${selected.code} — Seven HR Pillars`
              : "Seven HR Pillars"
          }
          action={
            provisional ? (
              <Badge
                variant="outline"
                className="border-warning/30 bg-warning/10 text-warning"
              >
                Partial data
              </Badge>
            ) : null
          }
        >
          {selected && (
            <Loading
              error={detail.error}
              loading={detail.loading && !detail.data}
            />
          )}
          {detail.data && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>HR Pillar</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {detail.data.pillars.map((p) => (
                    <SelectableSurface
                      as="tr"
                      key={p.pillar}
                      selection={{
                        type: "company_pillar_tile",
                        id: `company.${detail.data!.company.id}.pillar.${p.pillar}`,
                        label: `${detail.data!.company.code} · ${label(p.pillar)}`,
                        route: `/company?company=${detail.data!.company.id}`,
                        period,
                        refs: {
                          company_id: detail.data!.company.id,
                          company_code: detail.data!.company.code,
                          pillar: p.pillar,
                        },
                        dataSnapshot: {
                          pillar: p.pillar,
                          score: p.score,
                          status: p.status,
                        },
                      }}
                      className="border-b transition-colors hover:bg-muted/40 data-[selected=true]:bg-primary/5"
                    >
                      <TableCell className="font-medium">
                        {label(p.pillar)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmt(p.score)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={p.status as Status} />
                      </TableCell>
                    </SelectableSurface>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Card>
      </div>

      {selected && (
        <Card
          title={`Sub-KPI Drill-Down — ${selected.code}`}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Select
                items={[
                  { value: "all", label: "All pillars" },
                  ...(detail.data?.pillars.map((p) => ({
                    value: p.pillar,
                    label: label(p.pillar),
                  })) ?? []),
                ]}
                value={pillarFilter}
                onValueChange={(v) => setPillarFilter(String(v))}
              >
                <SelectTrigger className="h-9 w-44 rounded-full">
                  <SelectValue placeholder="Pillar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Pillar: All</SelectItem>
                  {detail.data?.pillars.map((p) => (
                    <SelectItem key={p.pillar} value={p.pillar}>
                      {label(p.pillar)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                items={[
                  { value: "all", label: "All statuses" },
                  { value: "scored", label: "Scored" },
                  { value: "missing", label: "Missing / excluded" },
                ]}
                value={statusFilter}
                onValueChange={(v) => setStatusFilter(String(v))}
              >
                <SelectTrigger className="h-9 w-44 rounded-full">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Status: All</SelectItem>
                  <SelectItem value="scored">Scored</SelectItem>
                  <SelectItem value="missing">Missing / excluded</SelectItem>
                </SelectContent>
              </Select>
              <AskCopilotButton
                size="sm"
                variant="outline"
                className="h-9 rounded-full"
                selection={{
                  type: "company_detail_header",
                  id: `company.${selected.company_id}.ask`,
                  label: `${selected.code} · ${selected.name}`,
                  route: `/company?company=${selected.company_id}`,
                  period,
                  refs: {
                    company_id: selected.company_id,
                    company_code: selected.code,
                  },
                  dataSnapshot: {
                    score: selected.score,
                    status: selected.status,
                    pillar_coverage: selected.pillar_coverage,
                  },
                }}
              >
                Ask Co-Pilot about {selected.code}
              </AskCopilotButton>
            </div>
          }
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sub-KPI</TableHead>
                  <TableHead>Pillar</TableHead>
                  <TableHead className="text-right">Achieved</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead>Note</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredKpis.map((k) => (
                  <SelectableSurface
                    as="tr"
                    key={k.key}
                    selection={{
                      type: "kpi_row",
                      id: `kpi.${k.key}@company.${selected.company_id}`,
                      label: `${label(k.key)} · ${selected.code}`,
                      route: `/company?company=${selected.company_id}`,
                      period,
                      refs: {
                        company_id: selected.company_id,
                        company_code: selected.code,
                        pillar: k.pillar,
                        kpi_key: k.key,
                      },
                      dataSnapshot: {
                        key: k.key,
                        pillar: k.pillar,
                        score: k.score,
                        excluded_reason: k.excluded_reason,
                        achievement: k.achievement,
                      },
                    }}
                    className="border-b transition-colors hover:bg-muted/40 data-[selected=true]:bg-primary/5"
                  >
                    <TableCell className="font-medium">
                      {label(k.key)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {label(k.pillar)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmt(k.achievement)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmt(k.score)}
                    </TableCell>
                    <TableCell>
                      {k.excluded_reason ? (
                        <Badge variant="outline" className="text-xs">
                          {reasonLabel(k.excluded_reason)}
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="border-success/30 bg-success/10 text-xs text-success"
                        >
                          Scored
                        </Badge>
                      )}
                    </TableCell>
                  </SelectableSurface>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            An excluded KPI is left out and the remaining weights rescaled —
            never counted as zero. <strong>No source</strong> means no connected
            system supplies it.
          </p>
        </Card>
      )}

      {selected && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Key observation">
            <p className="text-sm leading-relaxed text-muted-foreground">
              {weakest
                ? `${selected.code}'s ${label(weakest.pillar)} pillar is ${weakest.status === "red" ? "off track" : weakest.status === "amber" ? "needs attention" : "leading"} at ${fmt(weakest.score)}.`
                : `${selected.code} does not yet have scored pillars for this period.`}
              {missingPillars > 0
                ? ` ${missingPillars} pillar${missingPillars === 1 ? "" : "s"} still lack data — validate source coverage before comparing IC ranks.`
                : " Source coverage looks complete for scored pillars."}
            </p>
          </Card>
          <Card
            title="Next step"
            action={
              <AskCopilotButton
                size="sm"
                className="rounded-full"
                selection={{
                  type: "company_detail_header",
                  id: `company.${selected.company_id}.next`,
                  label: `Investigate ${selected.code}`,
                  route: `/company?company=${selected.company_id}`,
                  period,
                  refs: {
                    company_id: selected.company_id,
                    company_code: selected.code,
                  },
                  dataSnapshot: {
                    score: selected.score,
                    group_score: groupScore,
                    delta,
                    weakest_pillar: weakest?.pillar ?? null,
                  },
                }}
              >
                Investigate in Co-Pilot →
              </AskCopilotButton>
            }
          >
            <p className="text-sm leading-relaxed text-muted-foreground">
              Ask the Co-Pilot to compare {selected.code} with the Group score
              {weakest
                ? ` and dig into ${label(weakest.pillar)} drivers`
                : ""}
              .
            </p>
          </Card>
        </div>
      )}
    </div>
  );
}

export default function CompanyPage() {
  return (
    <Suspense fallback={null}>
      <CompanyView />
    </Suspense>
  );
}
