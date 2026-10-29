"use client";
import { use } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, Loading } from "@/components/ui";
import { fmt, label, reasonLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Drilldown } from "@/lib/types";

export default function PillarPage({ params }: { params: Promise<{ pillar: string }> }) {
  const { pillar } = use(params);
  const [period] = usePeriod();
  const { data, error, loading } = useApi<Drilldown>(`/scorecard/pillars/${pillar}?period=${period}`);
  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-muted-foreground hover:underline">← Dashboard</Link>
      <h1 className="text-2xl font-semibold">{label(pillar)} <span className="text-base font-normal text-muted-foreground">{period}</span></h1>
      <Loading error={error} loading={loading} />
      {data?.kpis.map((k) => (
        <Card key={k.key} title={label(k.key)}>
          <dl className="mb-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
            <div><dt className="text-muted-foreground">Weight in pillar</dt><dd>{Math.round(k.weight * 100)}%</dd></div>
            <div><dt className="text-muted-foreground">Target</dt><dd>{fmt(k.target)} ({k.direction} is better)</dd></div>
            <div><dt className="text-muted-foreground">Group achievement</dt><dd>{fmt(k.group_achievement)}</dd></div>
            <div><dt className="text-muted-foreground">Group score</dt><dd>{k.group_excluded_reason ? `Excluded (${reasonLabel(k.group_excluded_reason).toLowerCase()})` : fmt(k.group_score)}</dd></div>
            <div><dt className="text-muted-foreground">Coverage</dt><dd>{k.coverage}/{k.companies.length} companies</dd></div>
          </dl>
          {k.no_source && (
            <Alert role="note" className="mb-3 bg-muted"><AlertDescription className="text-foreground">
              <strong>No source.</strong> No integration currently supplies this KPI, so it is left out of the
              score and the other KPIs&apos; weights are rescaled. It is not counted as zero.{" "}
              <Link href="/connections" className="underline">Check connections</Link>
            </AlertDescription></Alert>
          )}
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground">Companies</summary>
            <Table className="mt-2">
              <TableHeader><TableRow><TableHead>Company</TableHead><TableHead>Achievement</TableHead><TableHead>Score</TableHead></TableRow></TableHeader>
              <TableBody>
                {k.companies.map((c) => (
                  <TableRow key={c.company_id}>
                    <TableCell><Link className="hover:underline" href={`/companies/${c.company_id}`}>{c.code}</Link></TableCell>
                    <TableCell className="tabular-nums">{fmt(c.achievement)}</TableCell>
                    <TableCell className="tabular-nums">{c.excluded_reason ? <span className="text-muted-foreground">{reasonLabel(c.excluded_reason)}</span> : fmt(c.score)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
        </Card>
      ))}
    </div>
  );
}
