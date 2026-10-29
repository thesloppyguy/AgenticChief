import Link from "next/link";
import { Card, ScoreTile, StatusBadge } from "@/components/ui";
import { fmt, label } from "@/lib/format";
import type { ReportDoc } from "@/lib/types";

const sign = (n: number | null) => (n == null ? "—" : `${n > 0 ? "+" : ""}${fmt(n)}`);

export default function ReportView({ r }: { r: ReportDoc }) {
  const h = r.headline;
  return (
    <div className="space-y-6">
      {r.meta.synthetic_data && (
        <p role="note" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Synthetic data.</strong> This report is built on generated stub or seed data. Do not use it for decisions.
        </p>
      )}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <ScoreTile title="Group score" score={h.group_score} status={h.group_status}
          note={h.delta == null ? "no comparison" : `${sign(h.delta)} vs ${r.meta.previous_period}`} />
        {h.pillars.map((p) => (
          <ScoreTile key={p.pillar} title={label(p.pillar)} score={p.score} status={p.status}
            note={p.delta == null ? undefined : sign(p.delta)} />
        ))}
      </div>

      <Card title="Commentary"
        action={<span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
          {r.commentary.method === "ai" ? "AI-drafted · every number verified" : "Template from computed results"}</span>}>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{r.commentary.text}</p>
        {r.commentary.issues.length > 0 && r.commentary.method === "template" && (
          <p className="mt-2 text-xs text-slate-500">Why a template: {r.commentary.issues.join(", ")}</p>
        )}
      </Card>

      {r.caveats.length > 0 && (
        <Card title="Caveats"><ul className="list-disc pl-5 text-sm text-slate-700">{r.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul></Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title={`Off track (${r.attention.red_count})`}>
          <ul className="space-y-1 text-sm">
            {r.attention.red.slice(0, 10).map((c) => (
              <li key={c.code}><strong>{c.code}</strong> {fmt(c.score)} <span className="text-slate-500">
                · weakest {c.weakest_pillars.map((w) => `${label(w.pillar)} ${fmt(w.score)}`).join(", ")}</span>
                {r.attention.newly_red.includes(c.code) && <span className="ml-1"><StatusBadge status="red" /> new</span>}</li>
            ))}
            {r.attention.red.length === 0 && <li className="text-slate-500">None.</li>}
          </ul>
        </Card>
        <Card title="Movement vs last month">
          {r.meta.previous_period == null ? <p className="text-sm text-slate-500">First month of the fiscal year: nothing to compare.</p> : (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><h3 className="mb-1 text-xs uppercase text-slate-500">Improved</h3>
                {r.movers.improved.map((m) => <div key={m.code}>{m.code} {sign(m.delta)}</div>)}</div>
              <div><h3 className="mb-1 text-xs uppercase text-slate-500">Declined</h3>
                {r.movers.declined.map((m) => <div key={m.code}>{m.code} {sign(m.delta)}</div>)}</div>
            </div>
          )}
        </Card>
      </div>

      <Card title="Exceptions">
        <ul className="space-y-1 text-sm">
          {r.exceptions.no_source.length > 0 && <li><strong>No source ({r.exceptions.no_source.length}):</strong> {r.exceptions.no_source.map(label).join(", ")}. <Link href="/connections" className="underline">Connections</Link></li>}
          {r.exceptions.missing.slice(0, 8).map((m) => <li key={m.kpi}>Missing: {label(m.kpi)} for {m.missing_count} companies (e.g. {m.sample.slice(0, 4).join(", ")})</li>)}
          {r.exceptions.not_due.length > 0 && <li>Not yet due: {r.exceptions.not_due.map(label).join(", ")}</li>}
          {r.exceptions.low_coverage.count > 0 && <li>{r.exceptions.low_coverage.count} companies have a pillar with nothing scoreable</li>}
          {r.exceptions.ingestion_problems.map((p) => <li key={p.source}>Ingestion {p.status}: {p.source} ({p.failed} companies failed)</li>)}
        </ul>
      </Card>

      <Card title="Sources and lineage">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-500"><tr><th>Source</th><th>Mode</th><th>Last run</th><th>OK / failed</th></tr></thead>
          <tbody>{r.lineage.sources.map((s) => (
            <tr key={s.source} className="border-t border-slate-100"><td>{s.label}</td><td>{s.mode}</td>
              <td>{s.last_run?.status ?? "never"}</td><td>{s.last_run ? `${s.last_run.companies_ok} / ${s.last_run.companies_failed}` : "—"}</td></tr>
          ))}</tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">Records by origin: {Object.entries(r.lineage.data_origin).map(([k, v]) => `${k} ${v}`).join(" · ")}.
          Calculation version {r.meta.calc_version}; generated {new Date(r.meta.generated_at).toLocaleString()} by {r.meta.generated_by}.</p>
      </Card>
    </div>
  );
}
