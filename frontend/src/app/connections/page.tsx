"use client";
import { useState } from "react";
import Link from "next/link";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { useEffect } from "react";
import type { MockStatus, SourceStatus } from "@/lib/types";

const MODE: Record<SourceStatus["mode"], { text: string; style: string }> = {
  live: { text: "Live", style: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  stub: { text: "Stub data", style: "bg-amber-50 text-amber-800 ring-amber-200" },
  disabled: { text: "Disabled", style: "bg-slate-50 text-slate-600 ring-slate-200" },
  registry: { text: "Via registry", style: "bg-blue-50 text-blue-800 ring-blue-200" },
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
      <p className="text-sm text-slate-600">
        SuccessFactors, PeopleStrong, MyHealth and Hi5Plus are stood in for by endpoints served by this app. Claude ({data.model}) writes each company&apos;s HR profile the first
        time it is needed; the live adapters then read it over HTTP like a real system. Everything it produces is marked synthetic.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
        <span><strong>{data.generated}</strong> of {data.companies} companies generated ({data.ai} by AI{data.fallback ? `, ${data.fallback} fallback` : ""})</span>
        <span className="h-2 w-40 overflow-hidden rounded bg-slate-100"><span className="block h-full bg-slate-700" style={{ width: `${pct}%` }} /></span>
        <button disabled={running || !data.ai_configured} onClick={() => act(() => api("/mock-sources/admin/generate", { method: "POST" }))}
          className="rounded bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50">{running ? `Generating… ${data.job.done}` : "Generate with AI"}</button>
        <button disabled={running || data.generated === 0} className="text-red-800 underline disabled:opacity-40"
          onClick={() => window.confirm("Forget all generated company data? The next run will generate new data.") && act(() => api("/mock-sources/admin/data", { method: "DELETE" }))}>Reset</button>
      </div>
      {!data.ai_configured && <p className="mt-2 text-sm text-amber-800">No API key is configured on the server, so nothing can be generated.</p>}
      {data.job.result?.failed?.length ? <p role="alert" className="mt-2 text-sm text-red-700">Could not generate: {data.job.result.failed.join(", ")}</p> : null}
      {data.job.result?.error && <p role="alert" className="mt-2 text-sm text-red-700">The last run failed ({data.job.result.error}).</p>}
      {msg && <p role="alert" className="mt-2 text-sm text-red-700">{msg}</p>}
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
          <Link href="/connections/registry" className="text-sm underline">Open the capability registry (MCP, APIs, function tools)</Link>
        </div>
        <button onClick={run} disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
          {busy ? "Running…" : `Run ingestion for ${period}`}
        </button>
      </div>
      <p className="text-sm text-slate-600">
        Each source is <strong>live</strong> (its adapter calls the system, real or AI-generated), serves <strong>stub</strong> data, or is disabled.
        Live is switched on per source on the server (<code>INTEGRATIONS__&lt;SOURCE&gt;__ENABLED</code>). Admins with group-wide access only.
      </p>
      {msg && <p role="status" className="text-sm">{msg}</p>}
      <MockSources />
      <Loading error={error} loading={loading} />
      {data?.map((s) => (
        <Card key={s.source} title={s.label}
          action={<span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${s.data_origin ? MODE.stub.style : MODE[s.mode].style}`}>
            {s.data_origin && s.mode === "live" ? "Live · AI-generated data" : MODE[s.mode].text}</span>}>
          <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <div><dt className="text-slate-500">Live integration</dt><dd>{s.live_enabled ? "Enabled" : "Off (flag)"}</dd></div>
            <div><dt className="text-slate-500">Last run</dt>
              <dd>{s.last_run ? `${s.last_run.status} · ${s.last_run.period}` : "Never"}</dd></div>
            <div><dt className="text-slate-500">Companies ok / failed</dt>
              <dd>{s.last_run ? `${s.last_run.companies_ok} / ${s.last_run.companies_failed}` : "—"}</dd></div>
            <div><dt className="text-slate-500">Finished</dt>
              <dd>{s.last_run?.finished_at ? new Date(s.last_run.finished_at).toLocaleString() : "—"}</dd></div>
          </dl>
          <p className="mt-3 text-xs text-slate-500">Supplies: {s.kpis.map(label).join(", ")}</p>
          {!!s.taken_over_by_registry?.length && (
            <p className="mt-1 text-xs text-blue-800">Now supplied through the registry: {s.taken_over_by_registry.map(label).join(", ")}</p>
          )}
          {s.no_source_kpis.length > 0 && (
            <p className="mt-1 text-xs text-slate-700">
              <strong>No source:</strong> {s.no_source_kpis.map(label).join(", ")}
              {s.mode === "live" ? " (not in this source's mapping file)" : " (source is disabled)"}
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}
