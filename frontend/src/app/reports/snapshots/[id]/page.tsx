"use client";
import { use } from "react";
import Link from "next/link";
import ReportView from "@/components/ReportView";
import PinButton from "@/components/PinButton";
import { Loading } from "@/components/ui";
import { download } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { ReportDoc } from "@/lib/types";

interface Snap { id: number; kind: string; period: string; content_hash: string | null; verified: boolean | null; created_by: string; created_at: string; run_id: number | null; payload: ReportDoc }

export default function SnapshotPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading } = useApi<Snap>(`/reports/snapshots/${id}`);
  return (
    <div className="max-w-5xl space-y-6">
      <Link href="/reports" className="text-sm text-slate-500 hover:underline">← Reports</Link>
      <Loading error={error} loading={loading} />
      {data && (
        <>
          <div className="flex justify-end gap-2"><PinButton kind="snapshot" target={id} />
            {data.kind === "monthly_review" && <button onClick={() => download(`/reports/snapshots/${id}/pdf`, `monthly-review-${data.period}-published.pdf`)} className="rounded border border-slate-300 px-3 py-1.5 text-sm">Download PDF</button>}</div>
          <h1 className="text-2xl font-semibold">Published review <span className="text-base font-normal text-slate-500">{data.period} · snapshot #{data.id}</span></h1>
          <p role="status" className={`rounded p-3 text-sm ${data.verified === false ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-900"}`}>
            {data.verified === false
              ? "Integrity check FAILED: the stored report no longer matches its hash. Do not rely on it."
              : data.verified ? "Integrity verified: the stored report matches its hash." : "Not hashed (legacy snapshot)."}{" "}
            <code className="break-all text-xs">{data.content_hash}</code> Published by {data.created_by} on {new Date(data.created_at).toLocaleString()}. Snapshots are immutable.
          </p>
          {data.kind === "monthly_review" && <ReportView r={data.payload} />}
        </>
      )}
    </div>
  );
}
