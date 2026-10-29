"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface PinRow { id: number; kind: string; ref: string }

/** Toggle a bookmark for the thing on screen. Pins are personal. */
export default function PinButton({ kind, target, label }: { kind: string; target: string; label?: string }) {
  const pins = useApi<PinRow[]>("/pins");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const mine = pins.data?.find((p) => p.kind === kind && p.ref === target);

  async function toggle() {
    setBusy(true);
    setErr(null);
    try {
      if (mine) await api(`/pins/${mine.id}`, { method: "DELETE" });
      else await api("/pins", { method: "POST", body: JSON.stringify({ kind, ref: target, label }) });
      pins.reload();
    } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
    finally { setBusy(false); }
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button onClick={toggle} disabled={busy || pins.loading} aria-pressed={!!mine}
        className={`rounded border px-3 py-1.5 text-sm ${mine ? "border-slate-900 bg-slate-100" : "border-slate-300"} disabled:opacity-50`}>
        {mine ? "★ Pinned" : "☆ Pin"}
      </button>
      {err && <span role="alert" className="text-xs text-red-700">{err}</span>}
    </span>
  );
}
