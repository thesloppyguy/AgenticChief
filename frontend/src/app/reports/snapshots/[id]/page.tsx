"use client";
import { use } from "react";
import Link from "next/link";
import ReportView from "@/components/ReportView";
import PinButton from "@/components/PinButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
      <Link href="/reports" className="text-sm text-muted-foreground hover:underline">← Reports</Link>
      <Loading error={error} loading={loading} />
      {data && (
        <>
          <div className="flex justify-end gap-2"><PinButton kind="snapshot" target={id} />
            {data.kind === "monthly_review" && <Button variant="outline" size="sm" onClick={() => download(`/reports/snapshots/${id}/pdf`, `monthly-review-${data.period}-published.pdf`)}>Download PDF</Button>}</div>
          <h1 className="text-2xl font-semibold">Published review <span className="text-base font-normal text-muted-foreground">{data.period} · snapshot #{data.id}</span></h1>
          <Alert role="status" variant={data.verified === false ? "destructive" : "default"} className={data.verified === false ? "" : "border-success/30 bg-success/10 text-success"}><AlertDescription className="text-current">
            {data.verified === false
              ? "Integrity check FAILED: the stored report no longer matches its hash. Do not rely on it."
              : data.verified ? "Integrity verified: the stored report matches its hash." : "Not hashed (legacy snapshot)."}{" "}
            <code className="break-all text-xs">{data.content_hash}</code> Published by {data.created_by} on {new Date(data.created_at).toLocaleString()}. Snapshots are immutable.
          </AlertDescription></Alert>
          {data.kind === "monthly_review" && <ReportView r={data.payload} />}
        </>
      )}
    </div>
  );
}
