"use client";
import { useState } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { useEffect } from "react";
import type { MockStatus, SourceStatus } from "@/lib/types";

const MODE: Record<SourceStatus["mode"], { text: string; style: string }> = {
  live: { text: "Live", style: "border-success/30 bg-success/10 text-success" },
  stub: { text: "Stub data", style: "border-warning/30 bg-warning/10 text-warning" },
  disabled: { text: "Disabled", style: "bg-muted text-muted-foreground" },
  registry: { text: "Via registry", style: "bg-secondary text-secondary-foreground" },
};

function MockSources() {
  const { data, error, reload } = useApi<MockStatus>("/mock-sources/admin/status");
  const [msg, setMsg] = useState<string | null>(null);
  const running = data?.job.running;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(reload, 3000);  // progress while Claude generates
    return () => clearInterval(t);
  }, [running, reload]);
  if (error || !data) return null;  // not mounted on this deployment: nothing to show
  const act = async (fn: () => Promise<unknown>) => { setMsg(null); try { await fn(); reload(); } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); } };
  const pct = data.companies ? Math.round((data.generated / data.companies) * 100) : 0;
  return (
    <Card title="AI-generated source systems">
      <p className="text-sm text-muted-foreground">
        SuccessFactors, PeopleStrong, MyHealth and Hi5Plus are stood in for by endpoints served by this app. Claude ({data.model}) writes each company&apos;s HR profile the first
        time it is needed; the live adapters then read it over HTTP like a real system. Everything it produces is marked synthetic.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
        <span><strong>{data.generated}</strong> of {data.companies} companies generated ({data.ai} by AI{data.fallback ? `, ${data.fallback} fallback` : ""})</span>
        <span className="h-2 w-40 overflow-hidden rounded bg-muted"><span className="block h-full bg-primary" style={{ width: `${pct}%` }} /></span>
        <Button disabled={running || !data.ai_configured} onClick={() => act(() => api("/mock-sources/admin/generate", { method: "POST" }))}>
          {running ? `Generating… ${data.job.done}` : "Generate with AI"}</Button>
        <Button variant="destructive" disabled={running || data.generated === 0}
          onClick={() => window.confirm("Forget all generated company data? The next run will generate new data.") && act(() => api("/mock-sources/admin/data", { method: "DELETE" }))}>Reset</Button>
      </div>
      {!data.ai_configured && <p className="mt-2 text-sm text-warning">No API key is configured on the server, so nothing can be generated.</p>}
      {data.job.result?.failed?.length ? <Alert variant="destructive" className="mt-2"><AlertDescription>Could not generate: {data.job.result.failed.join(", ")}</AlertDescription></Alert> : null}
      {data.job.result?.error && <Alert variant="destructive" className="mt-2"><AlertDescription>The last run failed ({data.job.result.error}).</AlertDescription></Alert>}
      {msg && <Alert variant="destructive" className="mt-2"><AlertDescription>{msg}</AlertDescription></Alert>}
    </Card>
  );
}

export default function Connections() {
  const [period] = usePeriod();
  const { data, error, loading, reload } = useApi<SourceStatus[]>("/ingestion/status");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api<{ source: string; status: string; records_written: number }[]>("/ingestion/run", {
        method: "POST", body: JSON.stringify({ period }),
      });
      setMsg(res.map((r) => `${r.source}: ${r.status} (${r.records_written} records)`).join(" · "));
      reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Connections</h1>
          <Link href="/connections/registry" className="text-sm underline hover:text-foreground">Open the capability registry (MCP, APIs, function tools)</Link>
        </div>
        <Button onClick={run} disabled={busy}>
          {busy ? "Running…" : `Run ingestion for ${period}`}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Each source is <strong>live</strong> (its adapter calls the system, real or AI-generated), serves <strong>stub</strong> data, or is disabled.
        Live is switched on per source on the server (<code>INTEGRATIONS__&lt;SOURCE&gt;__ENABLED</code>). Admins with group-wide access only.
      </p>
      {msg && <Alert role="status"><AlertDescription>{msg}</AlertDescription></Alert>}
      <MockSources />
      <Loading error={error} loading={loading} />
      {data?.map((s) => (
        <Card key={s.source} title={s.label}
          action={<Badge variant="outline" className={cn(s.data_origin ? MODE.stub.style : MODE[s.mode].style)}>
            {s.data_origin && s.mode === "live" ? "Live · AI-generated data" : MODE[s.mode].text}</Badge>}>
          <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <div><dt className="text-muted-foreground">Live integration</dt><dd>{s.live_enabled ? "Enabled" : "Off (flag)"}</dd></div>
            <div><dt className="text-muted-foreground">Last run</dt>
              <dd>{s.last_run ? `${s.last_run.status} · ${s.last_run.period}` : "Never"}</dd></div>
            <div><dt className="text-muted-foreground">Companies ok / failed</dt>
              <dd>{s.last_run ? `${s.last_run.companies_ok} / ${s.last_run.companies_failed}` : "—"}</dd></div>
            <div><dt className="text-muted-foreground">Finished</dt>
              <dd>{s.last_run?.finished_at ? new Date(s.last_run.finished_at).toLocaleString() : "—"}</dd></div>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">Supplies: {s.kpis.map(label).join(", ")}</p>
          {!!s.taken_over_by_registry?.length && (
            <p className="mt-1 text-xs text-muted-foreground">Now supplied through the registry: {s.taken_over_by_registry.map(label).join(", ")}</p>
          )}
          {s.no_source_kpis.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              <strong>No source:</strong> {s.no_source_kpis.map(label).join(", ")}
              {s.mode === "live" ? " (not in this source's mapping file)" : " (source is disabled)"}
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}
