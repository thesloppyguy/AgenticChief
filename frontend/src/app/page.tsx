"use client";
import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading, ScoreTile, StatusBadge } from "@/components/ui";
import PinButton from "@/components/PinButton";
import { download } from "@/lib/api";
import { fmt, label, PILLAR_SHORT, STATUS_STYLE } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Scorecard } from "@/lib/types";

type StatusFilter = "all" | "green" | "amber" | "red" | "none";

function Dashboard() {
  const params = useSearchParams();
  const [storedPeriod, setPeriod] = usePeriod();
  const period = params.get("period") ?? storedPeriod;  // a pinned view brings its own period
  const { data, error, loading } = useApi<Scorecard>(`/scorecard?period=${period}`);
  const [q, setQ] = useState(params.get("q") ?? "");
  const [filter, setFilter] = useState<StatusFilter>((params.get("status") as StatusFilter) ?? "all");
  const [exportError, setExportError] = useState<string | null>(null);
  const viewPath = `/?${new URLSearchParams({ period, ...(filter !== "all" ? { status: filter } : {}), ...(q ? { q } : {}) })}`;
  const [asc, setAsc] = useState(true);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.companies
      .filter((c) => (c.code + c.name).toLowerCase().includes(q.toLowerCase()))
      .filter((c) => filter === "all" || (filter === "none" ? c.status == null : c.status === filter))
      .sort((a, b) => {
        if (a.score == null) return 1;
        if (b.score == null) return -1;
        return asc ? a.score - b.score : b.score - a.score;
      });
  }, [data, q, filter, asc]);

  const dist = useMemo(() => {
    const d = { green: 0, amber: 0, red: 0, none: 0 };
    data?.companies.forEach((c) => { d[c.status ?? "none"]++; });
    return d;
  }, [data]);
  const lowCoverage = data?.companies.filter((c) => c.pillar_coverage < 1).length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-semibold">Group HR Scorecard</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label>Period{" "}
            <input type="month" value={period} onChange={(e) => e.target.value && setPeriod(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1" />
          </label>
          <PinButton kind="view" target={viewPath} label={`Dashboard ${period}${filter !== "all" ? ` · ${filter}` : ""}${q ? ` · “${q}”` : ""}`} />
          {(["xlsx", "csv"] as const).map((f) => (
            <button key={f} className="rounded border border-slate-300 px-3 py-1.5" onClick={() => download(`/reports/export/scorecard.${f}?period=${period}`, `group-hr-scorecard-${period}.${f}`).then(() => setExportError(null)).catch((e) => setExportError(e.message))}>
              Export {f === "xlsx" ? "Excel" : "CSV"}
            </button>
          ))}
        </div>
      </div>
      <Loading error={error} loading={loading} />
      {exportError && <p role="alert" className="text-sm text-red-700">{exportError}</p>}
      {data?.synthetic_data && (
        <p role="note" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Synthetic data.</strong> Some or all values come from generated stub data because the
          source systems are not connected. Do not use these numbers for decisions.
        </p>
      )}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <ScoreTile title="Group score" score={data.group.score} status={data.group.status} withheld={data.group.status_withheld}
              note={data.group.pillar_coverage < 1
                ? `Only ${Math.round(data.group.pillar_coverage * 100)}% of weight scored`
                : `${data.group.companies_with_data}/${data.group.companies_in_scope} companies with data`} />
            {data.group.pillars.map((p) => (
              <ScoreTile key={p.pillar} title={label(p.pillar)} score={p.score}
                status={p.status} href={`/pillars/${p.pillar}`}
                note={p.eligible_weight < 1 ? `${Math.round(p.eligible_weight * 100)}% of KPIs scored` : undefined} />
            ))}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Companies by status">
              <ul className="flex flex-wrap gap-3 text-sm">
                {(["green", "amber", "red"] as const).map((s) => (
                  <li key={s} className={`rounded px-3 py-2 ring-1 ${STATUS_STYLE[s]}`}>
                    <span className="text-xl font-semibold tabular-nums">{dist[s]}</span> {s}
                  </li>
                ))}
                <li className="rounded bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
                  <span className="text-xl font-semibold tabular-nums">{dist.none}</span> no data
                </li>
              </ul>
            </Card>
            <Card title="Data quality">
              <p className="text-sm text-slate-700">
                {lowCoverage} of {data.companies.length} companies have at least one pillar with no scoreable KPI.
                Missing or not-yet-due KPIs are excluded and remaining weights rescaled — never treated as zero.
              </p>
              {data.no_source_kpis.length > 0 && (
                <p className="mt-2 text-sm text-slate-700">
                  <strong>{data.no_source_kpis.length} KPIs have no source</strong> ({data.no_source_kpis.map(label).join(", ")}).
                  They are excluded from every score until a source is connected.{" "}
                  <Link href="/connections" className="underline">Connections</Link>
                </p>
              )}
            </Card>
          </div>

          <Card title={`Companies (${rows.length})`}
            action={
              <div className="flex gap-2 text-sm">
                <input aria-label="Search companies" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)}
                  className="rounded border border-slate-300 px-2 py-1" />
                <select aria-label="Filter by status" value={filter} onChange={(e) => setFilter(e.target.value as StatusFilter)}
                  className="rounded border border-slate-300 px-2 py-1">
                  <option value="all">All</option><option value="red">Off track</option>
                  <option value="amber">Needs attention</option><option value="green">On track</option>
                  <option value="none">No data</option>
                </select>
              </div>
            }>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-slate-500">
                  <tr>
                    <th className="py-2">Company</th>
                    <th aria-sort={asc ? "ascending" : "descending"}>
                      <button onClick={() => setAsc(!asc)} className="underline decoration-dotted">Overall {asc ? "▲" : "▼"}</button>
                    </th>
                    <th>Status</th>
                    {data.group.pillars.map((p) => <th key={p.pillar} title={label(p.pillar)} className="px-1 text-center font-normal">{PILLAR_SHORT[p.pillar] ?? label(p.pillar)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.company_id} className="border-t border-slate-100">
                      <td className="py-1.5"><Link className="hover:underline" href={`/companies/${c.company_id}`}>{c.code} · {c.name}</Link></td>
                      <td className="tabular-nums">{fmt(c.score)}</td>
                      <td><StatusBadge status={c.status} withheld={c.status_withheld} /></td>
                      {c.pillars.map((p) => {
                        const s = p.status;
                        return (
                          <td key={p.pillar} className="px-1 text-center">
                            <span className={`inline-block w-12 rounded px-1 text-xs tabular-nums ring-1 ${s ? STATUS_STYLE[s] : "bg-slate-50 text-slate-400 ring-slate-100"}`}>
                              {fmt(p.score, 0)}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return <Suspense fallback={null}><Dashboard /></Suspense>;
}
