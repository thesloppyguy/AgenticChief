"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
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
      <Button
        variant={mine ? "secondary" : "outline"}
        onClick={toggle}
        disabled={busy || pins.loading}
        aria-pressed={!!mine}
        className="h-11 px-4 text-base"
      >
        {mine ? "★ Pinned" : "☆ Pin"}
      </Button>
      {err && <span role="alert" className="text-sm text-destructive">{err}</span>}
    </span>
  );
}
