import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function PanelShell({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>{children}</div>
  );
}

export function PanelIntro({
  title,
  description,
  count,
}: {
  title: string;
  description: string;
  count?: number | string;
}) {
  return (
    <div className="mb-4 flex shrink-0 items-end justify-between gap-3">
      <div className="min-w-0 space-y-1">
        <h3 className="text-balance text-xl font-semibold tracking-tight text-foreground">
          {title}
        </h3>
        <p className="max-w-xl text-pretty text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      </div>
      {count != null && (
        <span className="shrink-0 rounded-full bg-white px-3 py-1 text-xs font-medium text-foreground shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
          {count}
        </span>
      )}
    </div>
  );
}

export function PanelEmpty({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-3 rounded-2xl bg-muted/40 px-6 py-8 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-white text-foreground/70 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
        <Icon className="size-5" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="max-w-sm text-pretty text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      </div>
    </div>
  );
}

export function SideList({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "h-full min-h-0 space-y-4 overflow-y-auto rounded-2xl bg-white p-2 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SideListSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="px-2.5 pb-1.5 pt-1 text-[11px] font-semibold uppercase text-muted-foreground">
        {title}
      </div>
      <ul className="space-y-1">{children}</ul>
    </div>
  );
}

export function SideListItem({
  active,
  onClick,
  children,
  hint,
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left text-sm transition-colors",
          active
            ? "bg-muted font-medium text-foreground"
            : "text-foreground/80 hover:bg-muted/70 hover:text-foreground",
        )}
      >
        {Icon && (
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full",
              active
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-foreground/70",
            )}
          >
            <Icon className="size-3.5" />
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">{children}</span>
        {hint}
      </button>
    </li>
  );
}

export function DetailPane({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "h-full min-h-0 min-w-0 space-y-4 overflow-y-auto rounded-2xl bg-white p-5 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function StatusPill({ ok, label }: { ok: boolean; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        ok
          ? "bg-primary text-primary-foreground"
          : "bg-muted text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          ok ? "bg-white/90" : "bg-foreground/30",
        )}
      />
      {label ?? (ok ? "On" : "Off")}
    </span>
  );
}

export function MetricCard({
  label,
  ok,
  value,
}: {
  label: string;
  ok: boolean;
  value?: string;
}) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-black/5 dark:bg-card dark:ring-white/10">
      <div className="mb-3 text-xs font-medium text-muted-foreground">{label}</div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-lg font-semibold text-foreground">
          {value ?? (ok ? "Ready" : "Idle")}
        </span>
        <StatusPill ok={ok} />
      </div>
    </div>
  );
}
