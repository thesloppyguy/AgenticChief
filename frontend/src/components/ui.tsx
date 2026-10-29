import type { ReactNode } from "react";
import { fmt, STATUS_STYLE, statusOf } from "@/lib/format";
import type { Status } from "@/lib/types";

export function StatusBadge({ status, withheld }: { status: Status; withheld?: boolean }) {
  const style = status ? STATUS_STYLE[status] : "bg-slate-50 text-slate-600 ring-slate-200";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${style}`}
      title={withheld ? "Too little of the scorecard could be scored to give a status" : undefined}>
      {withheld && !status ? "Low coverage" : statusOf(status)}
    </span>
  );
}

export function ScoreTile(props: { title: string; score: number | null; status: Status; withheld?: boolean; note?: string; href?: string }) {
  const body = (
    <div className="rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-400">
      <div className="text-sm text-slate-500">{props.title}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{fmt(props.score)}</div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <StatusBadge status={props.status} withheld={props.withheld} />
        {props.note && <span className="text-xs text-slate-500">{props.note}</span>}
      </div>
    </div>
  );
  return props.href ? <a href={props.href}>{body}</a> : body;
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      {(title || action) && (
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="font-medium">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Loading({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">{error}</p>;
  if (loading) return <p className="text-sm text-slate-500">Loading…</p>;
  return null;
}
