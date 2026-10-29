import Link from "next/link";
import type { ReactNode } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card as ShadCard, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fmt, STATUS_STYLE, statusOf } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Status } from "@/lib/types";

export function StatusBadge({ status, withheld }: { status: Status; withheld?: boolean }) {
  return (
    <Badge variant="outline" className={cn(status ? STATUS_STYLE[status] : "text-muted-foreground")}
      title={withheld ? "Too little of the scorecard could be scored to give a status" : undefined}>
      {withheld && !status ? "Low coverage" : statusOf(status)}
    </Badge>
  );
}

export function ScoreTile(props: { title: string; score: number | null; status: Status; withheld?: boolean; note?: string; href?: string }) {
  const body = (
    <ShadCard size="sm" className={cn(props.href && "transition-colors hover:bg-muted/50")}>
      <CardContent>
        <div className="text-sm text-muted-foreground">{props.title}</div>
        <div className="mt-1 text-3xl font-semibold tabular-nums">{fmt(props.score)}</div>
        <div className="mt-2 flex items-center justify-between gap-2">
          <StatusBadge status={props.status} withheld={props.withheld} />
          {props.note && <span className="text-xs text-muted-foreground">{props.note}</span>}
        </div>
      </CardContent>
    </ShadCard>
  );
  return props.href ? <Link href={props.href}>{body}</Link> : body;
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <ShadCard>
      {(title || action) && (
        <CardHeader className="border-b">
          <CardTitle>{title}</CardTitle>
          {action && <CardAction>{action}</CardAction>}
        </CardHeader>
      )}
      <CardContent>{children}</CardContent>
    </ShadCard>
  );
}

export function Loading({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>;
  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  return null;
}
