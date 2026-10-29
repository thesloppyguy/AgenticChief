"use client";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface PinRow { id: number; kind: string; ref: string; label: string; href: string; created_at: string }
const KIND: Record<string, string> = { run: "Monthly reviews", snapshot: "Published reports", session: "Sessions", skill: "Skills", agent: "Agents", view: "Dashboard views" };

export default function Pinned() {
  const { data, error, loading, reload } = useApi<PinRow[]>("/pins");
  const groups = Object.keys(KIND).map((k) => ({ kind: k, rows: (data ?? []).filter((p) => p.kind === k) })).filter((g) => g.rows.length);
  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Pinned</h1>
      <p className="text-sm text-muted-foreground">Your bookmarks. Pin a report, session, skill, agent or a filtered dashboard view from the page itself. Pins are private to you.</p>
      <Loading error={error} loading={loading && !data} />
      {groups.map((g) => (
        <Card key={g.kind} title={KIND[g.kind]}>
          <ul className="divide-y divide-border text-sm">
            {g.rows.map((p) => (
              <li key={p.id} className="flex items-center justify-between py-2">
                <Link href={p.href} className="hover:underline">{p.label}</Link>
                <Button variant="ghost" size="xs" className="text-muted-foreground" onClick={async () => { await api(`/pins/${p.id}`, { method: "DELETE" }); reload(); }}>Unpin</Button>
              </li>
            ))}
          </ul>
        </Card>
      ))}
      {data?.length === 0 && <p className="text-sm text-muted-foreground">Nothing pinned yet.</p>}
    </div>
  );
}
