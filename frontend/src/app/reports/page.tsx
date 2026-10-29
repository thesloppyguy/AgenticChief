"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { RunSummary, SnapshotRow } from "@/lib/types";

export default function Reports() {
  const [period] = usePeriod();
  const router = useRouter();
  const runs = useApi<RunSummary[]>("/workflows/runs");
  const snaps = useApi<SnapshotRow[]>("/reports/snapshots");
  const [msg, setMsg] = useState<string | null>(null);

  async function generate() {
    setMsg(null);
    try {
      const r = await api<RunSummary>("/workflows/monthly-review/runs", { method: "POST", body: JSON.stringify({ period }) });
      router.push(`/reports/runs/${r.id}`);
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  async function quickSnapshot() {
    try {
      await api(`/reports/snapshots?period=${period}`, { method: "POST" });
      setMsg(`Scorecard snapshot saved for ${period}.`);
      snaps.reload();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Failed"); }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Reports</h1>
      {msg && <p role="status" className="text-sm">{msg}</p>}

      <Card title="Monthly leadership review"
        action={<button onClick={generate} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white">Generate review for {period}</button>}>
        <p className="mb-3 text-sm text-slate-600">
          Compares this month with last, lists exceptions and source lineage, and drafts commentary that is only
          kept if every number in it matches the computed results. Publishing needs a second admin&apos;s approval.
        </p>
        <Loading error={runs.error} loading={runs.loading} />
        <ul className="divide-y divide-slate-100 text-sm">
          {runs.data?.slice(0, 8).map((r) => (
            <li key={r.id} className="flex justify-between py-2">
              <Link href={`/reports/runs/${r.id}`} className="hover:underline">#{r.id} · {r.period}</Link>
              <span className="text-slate-500">{label(r.status)} · {r.requested_by}</span>
            </li>
          ))}
          {runs.data?.length === 0 && <li className="py-2 text-slate-500">No reviews yet.</li>}
        </ul>
      </Card>

      <Card title="Published snapshots"
        action={<button onClick={quickSnapshot} className="text-sm underline">Save scorecard snapshot for {period} (admin)</button>}>
        <Loading error={snaps.error} loading={snaps.loading} />
        <ul className="divide-y divide-slate-100 text-sm">
          {snaps.data?.map((s) => (
            <li key={s.id} className="flex justify-between gap-3 py-2">
              {s.kind === "monthly_review"
                ? <Link href={`/reports/snapshots/${s.id}`} className="hover:underline">{s.period} · monthly review</Link>
                : <span>{s.period} · scorecard</span>}
              <span className="text-slate-500">calc v{s.calc_version} · <code>{s.content_hash?.slice(0, 8) ?? "—"}</code> · {s.created_by}</span>
            </li>
          ))}
          {snaps.data?.length === 0 && <li className="py-2 text-slate-500">Nothing published yet.</li>}
        </ul>
      </Card>
    </div>
  );
}
