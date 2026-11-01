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
  const empty = !status;
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 px-2.5 text-sm",
        status
          ? STATUS_STYLE[status]
          : "border-foreground/20 bg-muted font-normal text-foreground/70",
      )}
      title={withheld ? "Too little of the scorecard could be scored to give a status" : undefined}
    >
      {withheld && empty ? "Low coverage" : statusOf(status)}
    </Badge>
  );
}

export function ScoreTile(props: {
  title: string;
  score: number | null;
  status: Status;
  withheld?: boolean;
  note?: string;
  href?: string;
  accent?: boolean;
}) {
  const empty = props.score == null;
  const emptyLabel = props.withheld ? "Low coverage" : "No data";

  const body = (
    <ShadCard
      className={cn(
        "gap-0 rounded-2xl py-5 shadow-sm ring-black/5 [--card-spacing:--spacing(4)]",
        empty && !props.accent && "bg-muted/40",
        props.accent && "bg-neutral-900 text-white shadow-md ring-0 dark:bg-neutral-100 dark:text-neutral-900",
        props.href && "transition-shadow hover:shadow-md",
      )}
    >
      <CardContent className="flex flex-col gap-3">
        <div
          className={cn(
            "text-sm font-medium leading-snug",
            props.accent ? "text-white/70 dark:text-neutral-900/70" : "text-muted-foreground",
          )}
        >
          {props.title}
        </div>

        {empty ? (
          <div className="flex flex-col gap-1.5 pt-0.5">
            <div className="text-xl font-semibold tracking-tight">
              {emptyLabel}
            </div>
            {props.note && (
              <p
                className={cn(
                  "text-xs leading-snug",
                  props.accent ? "text-white/60 dark:text-neutral-900/60" : "text-muted-foreground",
                )}
              >
                {props.note}
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            <div className="text-3xl font-semibold tracking-tight tabular-nums">
              {fmt(props.score)}
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <StatusBadge status={props.status} withheld={props.withheld} />
              {props.note && (
                <span
                  className={cn(
                    "text-xs leading-snug",
                    props.accent ? "text-white/60 dark:text-neutral-900/60" : "text-muted-foreground",
                  )}
                >
                  {props.note}
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </ShadCard>
  );

  return props.href ? (
    <Link href={props.href} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

export function Card({ title, children, action, className, contentClassName }: {
  title?: string; children: ReactNode; action?: ReactNode; className?: string; contentClassName?: string;
}) {
  return (
    <ShadCard className={cn("min-h-0 gap-5 py-6 text-base [--card-spacing:--spacing(5)]", className)}>
      {(title || action) && (
        <CardHeader className="gap-2">
          <CardTitle className="text-lg">{title}</CardTitle>
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
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0 space-y-1.5">
        <h1 className="text-balance text-[1.75rem] font-semibold tracking-tight text-foreground md:text-3xl">
          {title}
        </h1>
        {subtitle && (
          <p className="max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground md:text-base">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
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
