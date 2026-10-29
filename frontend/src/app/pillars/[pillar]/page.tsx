"use client";
import { use } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
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
      <Link href="/" className="text-sm text-slate-500 hover:underline">← Dashboard</Link>
      <h1 className="text-2xl font-semibold">{label(pillar)} <span className="text-base font-normal text-slate-500">{period}</span></h1>
      <Loading error={error} loading={loading} />
      {data?.kpis.map((k) => (
        <Card key={k.key} title={label(k.key)}>
          <dl className="mb-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
            <div><dt className="text-slate-500">Weight in pillar</dt><dd>{Math.round(k.weight * 100)}%</dd></div>
            <div><dt className="text-slate-500">Target</dt><dd>{fmt(k.target)} ({k.direction} is better)</dd></div>
            <div><dt className="text-slate-500">Group achievement</dt><dd>{fmt(k.group_achievement)}</dd></div>
            <div><dt className="text-slate-500">Group score</dt><dd>{k.group_excluded_reason ? `Excluded (${reasonLabel(k.group_excluded_reason).toLowerCase()})` : fmt(k.group_score)}</dd></div>
            <div><dt className="text-slate-500">Coverage</dt><dd>{k.coverage}/{k.companies.length} companies</dd></div>
          </dl>
          {k.no_source && (
            <p role="note" className="mb-3 rounded bg-slate-100 p-2 text-sm text-slate-700">
              <strong>No source.</strong> No integration currently supplies this KPI, so it is left out of the
              score and the other KPIs&apos; weights are rescaled. It is not counted as zero.{" "}
              <Link href="/connections" className="underline">Check connections</Link>
            </p>
          )}
          <details>
            <summary className="cursor-pointer text-sm text-slate-600">Companies</summary>
            <table className="mt-2 w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th>Company</th><th>Achievement</th><th>Score</th></tr></thead>
              <tbody>
                {k.companies.map((c) => (
                  <tr key={c.company_id} className="border-t border-slate-100">
                    <td><Link className="hover:underline" href={`/companies/${c.company_id}`}>{c.code}</Link></td>
                    <td className="tabular-nums">{fmt(c.achievement)}</td>
                    <td className="tabular-nums">{c.excluded_reason ? <span className="text-slate-400">{reasonLabel(c.excluded_reason)}</span> : fmt(c.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </Card>
      ))}
    </div>
  );
}
