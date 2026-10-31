import Link from "next/link";
import type { ReactNode } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card as ShadCard, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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

export function ScoreTile(props: { title: string; score: number | null; status: Status; withheld?: boolean; note?: string; href?: string; accent?: boolean }) {
  const body = (
    <ShadCard size="sm" className={cn("h-full", props.accent && "bg-accent text-accent-foreground ring-0", props.href && "transition-shadow hover:shadow-md")}>
      <CardContent className="flex h-full flex-col justify-between gap-2">
        <div className={cn("text-sm", props.accent ? "text-accent-foreground/70" : "text-muted-foreground")}>{props.title}</div>
        <div className="text-3xl font-semibold tracking-tight tabular-nums">{fmt(props.score)}</div>
        <div className="flex items-center justify-between gap-2">
          <span className={cn(props.accent && "rounded-md bg-[#062F28]")}>
            <StatusBadge status={props.status} withheld={props.withheld} />
          </span>
          {props.note && <span className={cn("text-xs", props.accent ? "text-accent-foreground/70" : "text-muted-foreground")}>{props.note}</span>}
        </div>
      </CardContent>
    </ShadCard>
  );
  return props.href ? <Link href={props.href} className="block h-full">{body}</Link> : body;
}

export function Card({ title, children, action, className, contentClassName }: {
  title?: string; children: ReactNode; action?: ReactNode; className?: string; contentClassName?: string;
}) {
  return (
    <ShadCard className={cn("min-h-0", className)}>
      {(title || action) && (
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {action && <CardAction>{action}</CardAction>}
        </CardHeader>
      )}
      <CardContent className={cn("min-h-0", contentClassName)}>{children}</CardContent>
    </ShadCard>
  );
}

/** Page title row: title + subtitle on the left, actions on the right. */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Loading({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>;
  if (loading) return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true" aria-label="Loading">
      {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
    </div>
  );
  return null;
}
