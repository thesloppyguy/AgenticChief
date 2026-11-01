"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading, PageHeader, ScoreTile, StatusBadge } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fmt, label, reasonLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { CompanyCard, Drilldown, Scorecard } from "@/lib/types";

const PILLARS = [
  "talent_acquisition", "performance_management", "learning_development",
  "organizational_effectiveness", "talent_management", "engagement_wellness", "retention",
];

interface CompanyDetail extends CompanyCard {
  company: { id: number; code: string; name: string };
  values: Record<string, { achievement: number | null; numerator: number | null; denominator: number | null }>;
}

function Companies({ period }: { period: string }) {
  const params = useSearchParams();
  const card = useApi<Scorecard>(`/scorecard?period=${period}`);
  const [picked, setPicked] = useState<number | null>(
    params.get("company") ? Number(params.get("company")) : null,
  );
  const selected = picked ?? card.data?.companies[0]?.company_id ?? null;
  const detail = useApi<CompanyDetail>(
    selected ? `/scorecard/companies/${selected}?period=${period}` : null,
  );

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <Card title={`Companies${card.data ? ` (${card.data.companies.length})` : ""}`}>
        <Loading error={card.error} loading={card.loading && !card.data} />
        <ul className="max-h-[calc(100vh-14rem)] space-y-0.5 overflow-y-auto pr-1">
          {card.data?.companies.map((c) => (
            <li key={c.company_id}>
              <button onClick={() => setPicked(c.company_id)}
                className={cn("flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-muted",
                  selected === c.company_id && "bg-secondary font-medium")}>
                <span className="truncate">{c.code}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular-nums">{fmt(c.score)}</span>
                  <StatusBadge status={c.status} withheld={c.status_withheld} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <div className="space-y-4">
        {selected && <Loading error={detail.error} loading={detail.loading && !detail.data} />}
        {detail.data && (
          <>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">{detail.data.company.name}</h2>
              <p className="text-sm text-muted-foreground">
                {detail.data.company.code} · scored on{" "}
                {Math.round(detail.data.pillar_coverage * 100)}% of the scorecard&apos;s weight
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <ScoreTile accent title="Overall" score={detail.data.score} status={detail.data.status}
                withheld={detail.data.status_withheld} />
              {detail.data.pillars.map((p) => (
                <ScoreTile key={p.pillar} title={label(p.pillar)} score={p.score} status={p.status} />
              ))}
            </div>
            <Card title="Every KPI" contentClassName="[&_[data-slot=table-container]]:max-h-[28rem] [&_[data-slot=table-container]]:overflow-y-auto [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-muted">
              <div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>KPI</TableHead>
                      <TableHead>Pillar</TableHead>
                      <TableHead className="text-right">Achieved</TableHead>
                      <TableHead className="text-right">Score</TableHead>
                      <TableHead>Note</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.data.pillars.flatMap((p) =>
                      p.kpis.map((k) => (
                        <TableRow key={k.key}>
                          <TableCell className="font-medium">{label(k.key)}</TableCell>
                          <TableCell className="text-muted-foreground">{label(p.pillar)}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmt(detail.data?.values[k.key]?.achievement ?? null)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{fmt(k.score)}</TableCell>
                          <TableCell>
                            {k.excluded_reason && (
                              <Badge variant="outline" className="text-xs">
                                {reasonLabel(k.excluded_reason)}
                              </Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      )),
                    )}
                  </TableBody>
                </Table>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                An excluded KPI is left out and the remaining weights rescaled — never counted as zero.
                <strong> No source</strong> means no connected system supplies it, so nobody can submit it.
              </p>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

function Pillars({ period }: { period: string }) {
  const params = useSearchParams();
  const [pillar, setPillar] = useState(params.get("pillar") ?? PILLARS[0]);
  const { data, error, loading } = useApi<Drilldown>(
    `/scorecard/pillars/${pillar}?period=${period}`,
  );

  return (
    <div className="space-y-4">
      <Select items={PILLARS.map((p) => ({ value: p, label: label(p) }))}
        value={pillar} onValueChange={(v) => setPillar(String(v))}>
        <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
        <SelectContent>
          {PILLARS.map((p) => <SelectItem key={p} value={p}>{label(p)}</SelectItem>)}
        </SelectContent>
      </Select>

      <Loading error={error} loading={loading && !data} />
      {data && (
        <Card title={`${label(pillar)} — every sub-KPI`}>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sub-KPI</TableHead>
                  <TableHead className="text-right">Weight</TableHead>
                  <TableHead className="text-right">Target</TableHead>
                  <TableHead className="text-right">Group achieved</TableHead>
                  <TableHead className="text-right">Group score</TableHead>
                  <TableHead className="text-right">Companies with a value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.kpis.map((k) => (
                  <TableRow key={k.key}>
                    <TableCell className="font-medium">
                      {label(k.key)}
                      {k.direction === "lower" && (
                        <span className="ml-1 text-xs text-muted-foreground">(lower is better)</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{Math.round(k.weight * 100)}%</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt(k.target)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt(k.group_achievement)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {k.group_excluded_reason
                        ? <Badge variant="outline" className="text-xs">{reasonLabel(k.group_excluded_reason)}</Badge>
                        : fmt(k.group_score)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {k.no_source ? "—" : `${k.coverage} / ${k.companies.length}`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}
    </div>
  );
}

function CompanyView() {
  const params = useSearchParams();
  const [period] = usePeriod();
  const [tab, setTab] = useState(params.get("tab") === "pillars" ? "pillars" : "companies");

  return (
    <div className="space-y-5">
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="gap-4">
        <PageHeader
          title="Company"
          subtitle="Drill from the group overview into one company, or into one pillar across every company."
          actions={
            <TabsList className="rounded-full">
              <TabsTrigger value="companies" className="rounded-full">By company</TabsTrigger>
              <TabsTrigger value="pillars" className="rounded-full">By pillar</TabsTrigger>
            </TabsList>
          }
        />
        <TabsContent value="companies"><Companies period={period} /></TabsContent>
        <TabsContent value="pillars"><Pillars period={period} /></TabsContent>
      </Tabs>
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
