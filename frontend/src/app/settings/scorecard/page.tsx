"use client";
import { useState } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Approval, ConfigOverview, ConfigPreview, ConfigVersion, KpiCatalogRow } from "@/lib/types";

const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";
const pct = (n: number) => `${Math.round(n * 1000) / 10}%`;

export default function ScorecardRules() {
  const [period] = usePeriod();
  const { data, error, loading, reload } = useApi<ConfigOverview>("/scorecard-config");
  const [f, setF] = useState<Record<string, string | boolean> | null>(null);
  const [weights, setWeights] = useState<Record<string, string>>({});
  const catalog = useApi<{ kpis: KpiCatalogRow[] }>("/kpis");
  const [kpiEdits, setKpiEdits] = useState<Record<string, { weight: string; target: string }>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string; href?: string } | null>(null);
  const [preview, setPreview] = useState<{ version: number; p: ConfigPreview } | null>(null);

  function startDraft() {
    if (!data) return;
    const r = data.active.rules;
    setF({ score_cap: r.score_cap == null ? "" : String(r.score_cap), green_min: String(r.green_min), amber_min: String(r.amber_min),
      min_coverage_for_status: String(r.min_coverage_for_status * 100), prorate_cumulative: r.prorate_cumulative,
      missing_ic_policy: r.missing_ic_policy, note: "" });
    setWeights(Object.fromEntries(Object.entries(r.pillar_weights).map(([k, v]) => [k, String(Math.round(v * 1000) / 10)])));
    setKpiEdits(Object.fromEntries((catalog.data?.kpis ?? []).map((k) => [k.key, { weight: String(Math.round(k.weight * 1000) / 10), target: String(k.target) }])));
  }
  const kpiRows = catalog.data?.kpis ?? [];
  const pillarSum = (pillar: string) => kpiRows.filter((k) => k.pillar === pillar).reduce((a, k) => a + (Number(kpiEdits[k.key]?.weight) || 0), 0);
  const sum = Object.values(weights).reduce((a, b) => a + (Number(b) || 0), 0);

  async function saveDraft(e: React.FormEvent) {
    e.preventDefault();
    if (!f || !data) return;
    setMsg(null);
    // Only what differs from the built-in defaults is sent as an override.
    const kpi_overrides = Object.fromEntries(kpiRows.flatMap((k) => {
      const e = kpiEdits[k.key];
      if (!e) return [];
      const o: { weight?: number; target?: number } = {};
      if (Math.abs(Number(e.weight) / 100 - k.default_weight) > 1e-9) o.weight = Number(e.weight) / 100;
      if (k.target_steps.length === 0 && Number(e.target) !== k.default_target) o.target = Number(e.target);
      return Object.keys(o).length ? [[k.key, o]] : [];
    }));
    const rules = {
      kpi_overrides,
      score_cap: f.score_cap === "" ? null : Number(f.score_cap), green_min: Number(f.green_min), amber_min: Number(f.amber_min),
      min_coverage_for_status: Number(f.min_coverage_for_status) / 100, prorate_cumulative: f.prorate_cumulative,
      missing_ic_policy: f.missing_ic_policy, pillar_weights: Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, Number(v) / 100])),
    };
    try {
      const d = await api<ConfigVersion>("/scorecard-config/drafts", { method: "POST", body: JSON.stringify({ rules, note: f.note }) });
      setMsg({ ok: true, text: `Draft v${d.version} saved. Preview its effect, then propose activating it.` });
      setF(null); reload();
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
  }

  async function doPreview(version: number) {
    try { setPreview({ version, p: await api<ConfigPreview>(`/scorecard-config/${version}/preview?period=${period}`) }); }
    catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
  }

  async function propose(version: number) {
    try {
      const r = await api<{ verdict: string; reason: string; approval: Approval }>("/approvals", { method: "POST", body: JSON.stringify({ action: "activate_scorecard_config", args: { version } }) });
      setMsg(r.verdict === "deny" ? { ok: false, text: r.reason } : { ok: true, text: "Sent for approval. A different admin must approve it.", href: `/approvals?id=${r.approval.id}` });
    } catch (err) { setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" }); }
  }

  const rules = data?.active.rules;
  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Scorecard rules</h1>
      <p className="text-sm text-slate-600">These rules decide every score, status and report. A change is drafted, previewed against real data, and only takes effect once a second admin approves it. Published report snapshots keep the rules they were built with.</p>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-emerald-700" : "text-red-700"}`}>{msg.text} {msg.href && <Link href={msg.href} className="underline">Open request</Link>}</p>}
      <Loading error={error} loading={loading && !data} />

      {rules && data && (
        <Card title={`Active rules · v${data.active.version}${data.active.built_in ? " (built in)" : ""}`} action={!f && <button onClick={startDraft} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white">Draft a change</button>}>
          <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
            <div><dt className="text-slate-500">Status thresholds</dt><dd>Green ≥ {rules.green_min} · Amber ≥ {rules.amber_min}</dd></div>
            <div><dt className="text-slate-500">Score cap</dt><dd>{rules.score_cap == null ? "None (scores can exceed 100)" : rules.score_cap}</dd></div>
            <div><dt className="text-slate-500">Minimum coverage for a status</dt><dd>{rules.min_coverage_for_status === 0 ? "None" : pct(rules.min_coverage_for_status)}</dd></div>
            <div><dt className="text-slate-500">Year-to-date targets</dt><dd>{rules.prorate_cumulative ? "Pro-rated by month" : "Full-year target all year"}</dd></div>
            <div><dt className="text-slate-500">Companies with no value</dt><dd>{rules.missing_ic_policy === "exclude" ? "Left out of the Group average" : "Counted as zero"}</dd></div>
            <div className="col-span-2 md:col-span-3"><dt className="text-slate-500">Pillar weights</dt>
              <dd>{Object.entries(rules.pillar_weights).map(([k, v]) => `${label(k)} ${pct(v)}`).join(" · ")}</dd></div>
          </dl>
        </Card>
      )}

      {f && (
        <Card title="New draft">
          <form onSubmit={saveDraft} className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <label>Green from<input type="number" step="any" value={String(f.green_min)} onChange={(e) => setF({ ...f, green_min: e.target.value })} className={input} /></label>
              <label>Amber from<input type="number" step="any" value={String(f.amber_min)} onChange={(e) => setF({ ...f, amber_min: e.target.value })} className={input} /></label>
              <label>Score cap (blank = none)<input type="number" step="any" value={String(f.score_cap)} onChange={(e) => setF({ ...f, score_cap: e.target.value })} className={input} /></label>
              <label>Min. coverage for a status (%)<input type="number" min="0" max="100" value={String(f.min_coverage_for_status)} onChange={(e) => setF({ ...f, min_coverage_for_status: e.target.value })} className={input} /></label>
              <label>Companies with no value<select value={String(f.missing_ic_policy)} onChange={(e) => setF({ ...f, missing_ic_policy: e.target.value })} className={input}><option value="exclude">Leave out of the average</option><option value="zero">Count as zero</option></select></label>
              <label className="flex items-end gap-2 pb-1"><input type="checkbox" checked={!!f.prorate_cumulative} onChange={(e) => setF({ ...f, prorate_cumulative: e.target.checked })} /> Pro-rate year-to-date targets</label>
            </div>
            <fieldset><legend className="text-slate-600">Pillar weights (%): <span className={Math.abs(sum - 100) < 0.05 ? "text-emerald-700" : "font-medium text-red-700"}>total {Math.round(sum * 10) / 10}%</span></legend>
              <div className="mt-1 grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.keys(weights).map((k) => <label key={k}>{label(k)}<input type="number" step="any" value={weights[k]} onChange={(e) => setWeights({ ...weights, [k]: e.target.value })} className={input} /></label>)}
              </div></fieldset>
            {kpiRows.length > 0 && (
              <fieldset><legend className="text-slate-600">KPI weights (% of their pillar) and targets</legend>
                {Object.keys(weights).map((pillar) => {
                  const sum = pillarSum(pillar);
                  const ok = Math.abs(sum - 100) < 0.05;
                  return (
                    <div key={pillar} className="mt-3">
                      <div className="flex items-baseline justify-between text-xs"><strong>{label(pillar)}</strong>
                        <span className={ok ? "text-emerald-700" : "font-medium text-red-700"}>weights total {Math.round(sum * 10) / 10}%{ok ? "" : " — must be 100%"}</span></div>
                      <table className="mt-1 w-full text-xs"><tbody>
                        {kpiRows.filter((k) => k.pillar === pillar).map((k) => {
                          const e = kpiEdits[k.key] ?? { weight: "", target: "" };
                          const changed = Math.abs(Number(e.weight) / 100 - k.default_weight) > 1e-9 || Number(e.target) !== k.default_target;
                          return (
                            <tr key={k.key} className={`border-t border-slate-100 ${changed ? "bg-amber-50" : ""}`}>
                              <td className="py-1 pr-2">{label(k.key)}{changed && <span className="ml-1 text-amber-800">(changed)</span>}</td>
                              <td className="w-24"><input aria-label={`${label(k.key)} weight`} type="number" step="any" value={e.weight} onChange={(ev) => setKpiEdits({ ...kpiEdits, [k.key]: { ...e, weight: ev.target.value } })} className="w-full rounded border border-slate-300 px-1 py-0.5" /></td>
                              <td className="w-28 pl-2"><input aria-label={`${label(k.key)} target`} type="number" step="any" value={e.target} disabled={k.target_steps.length > 0}
                                title={k.target_steps.length ? "Follows the April / October calendar rule" : `Default ${k.default_target} (${k.direction} is better)`}
                                onChange={(ev) => setKpiEdits({ ...kpiEdits, [k.key]: { ...e, target: ev.target.value } })} className="w-full rounded border border-slate-300 px-1 py-0.5 disabled:bg-slate-100" /></td>
                            </tr>);
                        })}
                      </tbody></table>
                    </div>);
                })}
              </fieldset>)}
            <label className="block">Why (shown to the approver)<input maxLength={300} value={String(f.note)} onChange={(e) => setF({ ...f, note: e.target.value })} className={input} /></label>
            <div className="flex gap-2"><button className="rounded bg-slate-900 px-3 py-1.5 text-white">Save draft</button>
              <button type="button" onClick={() => setF(null)} className="rounded border border-slate-300 px-3 py-1.5">Cancel</button></div>
          </form>
        </Card>
      )}

      <Card title="Versions">
        <ul className="divide-y divide-slate-100 text-sm">
          {data?.versions.map((v) => (
            <li key={v.version} className="space-y-2 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><strong>v{v.version}</strong> · {v.status} · {v.created_by}{v.note ? ` · “${v.note}”` : ""}</span>
                {v.status === "draft" && <span className="flex gap-3"><button className="underline" onClick={() => doPreview(v.version)}>Preview impact ({period})</button>
                  <button className="underline" onClick={() => propose(v.version)}>Propose activation</button></span>}
              </div>
              {preview?.version === v.version && (
                <div className="rounded bg-slate-50 p-3 text-xs">
                  <p><strong>{preview.p.companies_changing_status}</strong> companies would change status for {preview.p.period}. Group score {preview.p.active.group_score?.toFixed(1) ?? "—"} → {preview.p.draft.group_score?.toFixed(1) ?? "—"}.</p>
                  <p className="mt-1">Now: {Object.entries(preview.p.active.distribution).map(([k, n]) => `${k} ${n}`).join(", ")}<br />With this draft: {Object.entries(preview.p.draft.distribution).map(([k, n]) => `${k} ${n}`).join(", ")}</p>
                  {preview.p.examples.length > 0 && <p className="mt-1 text-slate-600">e.g. {preview.p.examples.slice(0, 6).map((x) => `${x.code} ${x.from ?? "none"}→${x.to ?? "none"}`).join(", ")}</p>}
                </div>)}
            </li>))}
          {data?.versions.length === 0 && <li className="py-2 text-slate-500">No changes yet. The built-in defaults are in force.</li>}
        </ul>
      </Card>
    </div>
  );
}
