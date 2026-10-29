"use client";
import { use } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading, ScoreTile } from "@/components/ui";
import { fmt, label, reasonLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Overall } from "@/lib/types";

type Company = Overall & { company: { id: number; code: string; name: string }; values: Record<string, { achievement: number | null }> };

export default function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [period] = usePeriod();
  const { data, error, loading } = useApi<Company>(`/scorecard/companies/${id}?period=${period}`);
  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-slate-500 hover:underline">← Dashboard</Link>
      <Loading error={error} loading={loading} />
      {data && (
        <>
          <h1 className="text-2xl font-semibold">{data.company.code} · {data.company.name}</h1>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <ScoreTile title="Overall" score={data.score} status={data.status} withheld={data.status_withheld}
              note={`${Math.round(data.pillar_coverage * 100)}% of weight scored`} />
            {data.pillars.map((p) => <ScoreTile key={p.pillar} title={label(p.pillar)} score={p.score} status={p.status} />)}
          </div>
          <Card title="Sub-KPIs">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th>Pillar</th><th>KPI</th><th>Achievement</th><th>Score</th></tr></thead>
              <tbody>
                {data.pillars.flatMap((p) => p.kpis.map((k) => (
                  <tr key={k.key} className="border-t border-slate-100">
                    <td>{label(p.pillar)}</td><td>{label(k.key)}</td>
                    <td className="tabular-nums">{fmt(data.values[k.key]?.achievement)}</td>
                    <td className="tabular-nums">{k.excluded_reason ? <span className="text-slate-400">{reasonLabel(k.excluded_reason)}</span> : fmt(k.score)}</td>
                  </tr>
                )))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
