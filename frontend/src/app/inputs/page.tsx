"use client";
import { useState } from "react";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";

interface Company { id: number; code: string; name: string }
const KPIS = ["cost_per_hire", "top_talent_review", "idps_top_talent", "gptw_score"];

export default function Inputs() {
  const [period] = usePeriod();
  const companies = useApi<Company[]>("/companies");
  const [companyId, setCompanyId] = useState("");
  const [kpi, setKpi] = useState(KPIS[0]);
  const [f, setF] = useState({ value: "", cost: "", hires: "", reviewed: "true", date: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const hist = useApi<{ kpi_key: string; period: string; user: string; at: string; old: { achievement: number | null } | null; new: { achievement: number | null } }[]>(
    companyId ? `/inputs/history?company_id=${companyId}` : null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = { company_id: Number(companyId), period, kpi_key: kpi };
    if (kpi === "cost_per_hire") { body.recruitment_cost = Number(f.cost); body.hires = Number(f.hires); }
    else if (kpi === "top_talent_review") { body.reviewed = f.reviewed === "true"; if (f.date) body.review_date = f.date; }
    else body.value = Number(f.value);
    try {
      await api("/inputs", { method: "POST", body: JSON.stringify(body) });
      setMsg({ ok: true, text: "Saved." });
      hist.reload();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Failed" });
    }
  }

  const input = "w-full rounded border border-slate-300 px-2 py-1";
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Manual inputs <span className="text-base font-normal text-slate-500">{period}</span></h1>
      <p className="text-sm text-slate-600">Editors only. Every change keeps the previous value, who changed it and when.</p>
      <Loading error={companies.error} loading={companies.loading} />
      <Card>
        <form onSubmit={submit} className="space-y-3 text-sm">
          <label className="block">Company
            <select required value={companyId} onChange={(e) => setCompanyId(e.target.value)} className={input}>
              <option value="">Select…</option>
              {companies.data?.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
            </select>
          </label>
          <label className="block">KPI
            <select value={kpi} onChange={(e) => setKpi(e.target.value)} className={input}>
              {KPIS.map((k) => <option key={k} value={k}>{label(k)}</option>)}
            </select>
          </label>
          {kpi === "cost_per_hire" && (
            <div className="grid grid-cols-2 gap-3">
              <label>Recruitment cost (₹)<input required type="number" min="0" value={f.cost} onChange={(e) => setF({ ...f, cost: e.target.value })} className={input} /></label>
              <label>Hires<input required type="number" min="0" step="1" value={f.hires} onChange={(e) => setF({ ...f, hires: e.target.value })} className={input} /></label>
            </div>
          )}
          {kpi === "top_talent_review" && (
            <div className="grid grid-cols-2 gap-3">
              <label>Review held<select value={f.reviewed} onChange={(e) => setF({ ...f, reviewed: e.target.value })} className={input}><option value="true">Yes</option><option value="false">No</option></select></label>
              <label>Date<input type="date" required={f.reviewed === "true"} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} className={input} /></label>
            </div>
          )}
          {(kpi === "idps_top_talent" || kpi === "gptw_score") && (
            <label className="block">{kpi === "gptw_score" ? "Trust Index score" : "IDPs created (year to date)"}
              <input required type="number" min="0" step="any" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} className={input} />
            </label>
          )}
          {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-emerald-700" : "text-red-700"}>{msg.text}</p>}
          <button className="rounded bg-slate-900 px-4 py-2 text-white">Save</button>
        </form>
      </Card>
      {hist.data && hist.data.length > 0 && (
        <Card title="Change history">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500"><tr><th>When</th><th>KPI</th><th>Period</th><th>By</th><th>Old → New</th></tr></thead>
            <tbody>
              {hist.data.map((h, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td>{new Date(h.at).toLocaleString()}</td><td>{label(h.kpi_key)}</td><td>{h.period}</td><td>{h.user}</td>
                  <td className="tabular-nums">{h.old?.achievement ?? "—"} → {h.new.achievement ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
