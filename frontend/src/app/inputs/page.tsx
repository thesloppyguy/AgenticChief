"use client";
import { useState } from "react";
import { usePeriod } from "@/components/AppShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Manual inputs <span className="text-base font-normal text-muted-foreground">{period}</span></h1>
      <p className="text-sm text-muted-foreground">Editors only. Every change keeps the previous value, who changed it and when.</p>
      <Loading error={companies.error} loading={companies.loading} />
      <Card>
        <form onSubmit={submit} className="space-y-3 text-sm">
          <div className="space-y-1">
            <Label htmlFor="in-company">Company</Label>
            <Select value={companyId} onValueChange={(v) => setCompanyId(v ?? "")}
              items={companies.data?.map((c) => ({ value: String(c.id), label: `${c.code} · ${c.name}` })) ?? []}>
              <SelectTrigger id="in-company" className="w-full"><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent>
                {companies.data?.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.code} · {c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="in-kpi">KPI</Label>
            <Select value={kpi} onValueChange={(v) => { if (v) setKpi(v); }}
              items={KPIS.map((k) => ({ value: k, label: label(k) }))}>
              <SelectTrigger id="in-kpi" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {KPIS.map((k) => <SelectItem key={k} value={k}>{label(k)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {kpi === "cost_per_hire" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label htmlFor="in-cost">Recruitment cost (₹)</Label><Input id="in-cost" required type="number" min="0" value={f.cost} onChange={(e) => setF({ ...f, cost: e.target.value })} /></div>
              <div className="space-y-1"><Label htmlFor="in-hires">Hires</Label><Input id="in-hires" required type="number" min="0" step="1" value={f.hires} onChange={(e) => setF({ ...f, hires: e.target.value })} /></div>
            </div>
          )}
          {kpi === "top_talent_review" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="in-held">Review held</Label>
                <Select value={f.reviewed} onValueChange={(v) => { if (v) setF({ ...f, reviewed: v }); }}
                  items={[{ value: "true", label: "Yes" }, { value: "false", label: "No" }]}>
                  <SelectTrigger id="in-held" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="true">Yes</SelectItem><SelectItem value="false">No</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-1"><Label htmlFor="in-date">Date</Label><Input id="in-date" type="date" required={f.reviewed === "true"} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></div>
            </div>
          )}
          {(kpi === "idps_top_talent" || kpi === "gptw_score") && (
            <div className="space-y-1">
              <Label htmlFor="in-value">{kpi === "gptw_score" ? "Trust Index score" : "IDPs created (year to date)"}</Label>
              <Input id="in-value" required type="number" min="0" step="any" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />
            </div>
          )}
          {msg && <Alert variant={msg.ok ? "default" : "destructive"} role={msg.ok ? "status" : "alert"}><AlertDescription className={msg.ok ? "text-success" : undefined}>{msg.text}</AlertDescription></Alert>}
          <Button type="submit" disabled={!companyId}>Save</Button>
        </form>
      </Card>
      {hist.data && hist.data.length > 0 && (
        <Card title="Change history">
          <Table>
            <TableHeader><TableRow><TableHead>When</TableHead><TableHead>KPI</TableHead><TableHead>Period</TableHead><TableHead>By</TableHead><TableHead>Old → New</TableHead></TableRow></TableHeader>
            <TableBody>
              {hist.data.map((h, i) => (
                <TableRow key={i}>
                  <TableCell>{new Date(h.at).toLocaleString()}</TableCell><TableCell>{label(h.kpi_key)}</TableCell><TableCell>{h.period}</TableCell><TableCell>{h.user}</TableCell>
                  <TableCell className="tabular-nums">{h.old?.achievement ?? "—"} → {h.new.achievement ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
