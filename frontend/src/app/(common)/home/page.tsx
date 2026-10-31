"use client";
import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { Donut } from "@/components/charts";
import { Card, Loading, PageHeader, ScoreTile, StatusBadge } from "@/components/ui";
import PinButton from "@/components/PinButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { download } from "@/lib/api";
import { fmt, label, PILLAR_SHORT, STATUS_STYLE } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Scorecard } from "@/lib/types";

type StatusFilter = "all" | "green" | "amber" | "red" | "none";

const FILTER_ITEMS = [
  { value: "all", label: "All" },
  { value: "red", label: "Off track" },
  { value: "amber", label: "Needs attention" },
  { value: "green", label: "On track" },
  { value: "none", label: "No data" },
];

function Dashboard() {
  const params = useSearchParams();
  const [storedPeriod, setPeriod] = usePeriod();
  const period = params.get("period") ?? storedPeriod; // a pinned view brings its own period
  const { data, error, loading } = useApi<Scorecard>(
    `/scorecard?period=${period}`,
  );
  const [q, setQ] = useState(params.get("q") ?? "");
  const [filter, setFilter] = useState<StatusFilter>(
    (params.get("status") as StatusFilter) ?? "all",
  );
  const [exportError, setExportError] = useState<string | null>(null);
  const viewPath = `/?${new URLSearchParams({ period, ...(filter !== "all" ? { status: filter } : {}), ...(q ? { q } : {}) })}`;
  const [asc, setAsc] = useState(true);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.companies
      .filter((c) => (c.code + c.name).toLowerCase().includes(q.toLowerCase()))
      .filter(
        (c) =>
          filter === "all" ||
          (filter === "none" ? c.status == null : c.status === filter),
      )
      .sort((a, b) => {
        if (a.score == null) return 1;
        if (b.score == null) return -1;
        return asc ? a.score - b.score : b.score - a.score;
      });
  }, [data, q, filter, asc]);

  const dist = useMemo(() => {
    const d = { green: 0, amber: 0, red: 0, none: 0 };
    data?.companies.forEach((c) => {
      d[c.status ?? "none"]++;
    });
    return d;
  }, [data]);
  const lowCoverage =
    data?.companies.filter((c) => c.pillar_coverage < 1).length ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Group HR Scorecard"
        subtitle="Track the group's HR health by pillar and company."
        actions={
          <>
            <div className="flex items-center gap-2 text-sm">
              <Label htmlFor="period" className="text-muted-foreground">Period</Label>
              <Input
                id="period"
                type="month"
                value={period}
                onChange={(e) => e.target.value && setPeriod(e.target.value)}
                className="w-auto"
              />
            </div>
            <PinButton
              kind="view"
              target={viewPath}
              label={`Dashboard ${period}${filter !== "all" ? ` · ${filter}` : ""}${q ? ` · “${q}”` : ""}`}
            />
            {(["xlsx", "csv"] as const).map((f) => (
              <Button
                key={f}
                variant="outline"
                onClick={() =>
                  download(
                    `/reports/export/scorecard.${f}?period=${period}`,
                    `group-hr-scorecard-${period}.${f}`,
                  )
                    .then(() => setExportError(null))
                    .catch((e) => setExportError(e.message))
                }
              >
                Export {f === "xlsx" ? "Excel" : "CSV"}
              </Button>
            ))}
          </>
        }
      />
      <Loading error={error} loading={loading} />
      {exportError && (
        <Alert variant="destructive">
          <AlertDescription>{exportError}</AlertDescription>
        </Alert>
      )}
      {data?.synthetic_data && (
        <Alert
          role="note"
          className="border-warning/30 bg-warning/10 text-warning"
        >
          <AlertDescription className="text-warning">
            <strong>Synthetic data.</strong> Some or all values come from
            generated stub data because the source systems are not connected. Do
            not use these numbers for decisions.
          </AlertDescription>
        </Alert>
      )}
      {data && (
        <>
          <div className="grid gap-4 lg:grid-cols-12">
            <div className="lg:col-span-3">
            <ScoreTile
              accent
              title="Group score"
              score={data.group.score}
              status={data.group.status}
              withheld={data.group.status_withheld}
              note={
                data.group.pillar_coverage < 1
                  ? `Only ${Math.round(data.group.pillar_coverage * 100)}% of weight scored`
                  : `${data.group.companies_with_data}/${data.group.companies_in_scope} companies with data`
              }
            />
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:col-span-9">
            {data.group.pillars.map((p) => (
              <ScoreTile
                key={p.pillar}
                title={label(p.pillar)}
                score={p.score}
                status={p.status}
                href={`/company?tab=pillars&pillar=${p.pillar}`}
                note={
                  p.eligible_weight < 1
                    ? `${Math.round(p.eligible_weight * 100)}% of KPIs scored`
                    : undefined
                }
              />
            ))}
            </div>
          </div>

          <div className="grid items-start gap-4 lg:grid-cols-12">
          <div className="min-w-0 lg:col-span-8">
          <Card
            title={`Companies (${rows.length})`}
            contentClassName="[&_[data-slot=table-container]]:max-h-[34rem] [&_[data-slot=table-container]]:overflow-y-auto [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-muted"
            action={
              <div className="flex gap-2 text-sm">
                <Input
                  aria-label="Search companies"
                  placeholder="Search…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  className="w-auto"
                />
                <Select
                  items={FILTER_ITEMS}
                  value={filter}
                  onValueChange={(v) =>
                    v != null && setFilter(v as StatusFilter)
                  }
                >
                  <SelectTrigger aria-label="Filter by status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FILTER_ITEMS.map((i) => (
                      <SelectItem key={i.value} value={i.value}>
                        {i.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead aria-sort={asc ? "ascending" : "descending"}>
                    <Button
                      variant="link"
                      size="xs"
                      onClick={() => setAsc(!asc)}
                      className="px-0 decoration-dotted"
                    >
                      Overall {asc ? "▲" : "▼"}
                    </Button>
                  </TableHead>
                  <TableHead>Status</TableHead>
                  {data.group.pillars.map((p) => (
                    <TableHead
                      key={p.pillar}
                      title={label(p.pillar)}
                      className="px-1 text-center font-normal"
                    >
                      {PILLAR_SHORT[p.pillar] ?? label(p.pillar)}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((c) => (
                  <TableRow key={c.company_id}>
                    <TableCell>
                      <Link
                        className="block max-w-[8.5rem] truncate hover:underline"
                        href={`/company?company=${c.company_id}`}
                      >
                        {c.code} · {c.name}
                      </Link>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {fmt(c.score)}
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        status={c.status}
                        withheld={c.status_withheld}
                      />
                    </TableCell>
                    {c.pillars.map((p) => {
                      const s = p.status;
                      return (
                        <TableCell key={p.pillar} className="px-1 text-center">
                          <span
                            className={cn(
                              "inline-block w-10 rounded-md border px-1 text-xs tabular-nums",
                              s
                                ? STATUS_STYLE[s]
                                : "bg-muted text-muted-foreground",
                            )}
                          >
                            {fmt(p.score, 0)}
                          </span>
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          </div>
            <div className="space-y-4 lg:col-span-4">
              <Card title="Companies by status">
                <div className="flex items-center gap-5">
                  <Donut
                    segments={[
                      { value: dist.green, color: "var(--accent)", label: "On track" },
                      { value: dist.amber, color: "var(--warning)", label: "Needs attention" },
                      { value: dist.red, color: "var(--destructive)", label: "Off track" },
                      { value: dist.none, color: "var(--muted-foreground)", label: "No data" },
                    ]}
                    center={
                      <>
                        <div className="text-2xl font-semibold tabular-nums">{data.companies.length}</div>
                        <div className="text-xs text-muted-foreground">companies</div>
                      </>
                    }
                  />
                  <ul className="flex-1 space-y-2 text-sm">
                    {[
                      ["On track", dist.green, "var(--accent)"],
                      ["Needs attention", dist.amber, "var(--warning)"],
                      ["Off track", dist.red, "var(--destructive)"],
                      ["No data", dist.none, "var(--muted-foreground)"],
                    ].map(([name, n, color]) => (
                      <li key={name as string} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2">
                          <span className="size-2.5 rounded-full" style={{ background: color as string }} />
                          {name}
                        </span>
                        <span className="font-semibold tabular-nums">{n}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </Card>
              <Card title="Data quality">
                <p className="text-sm text-muted-foreground">
                  {lowCoverage} of {data.companies.length} companies have at least
                  one pillar with no scoreable KPI. Missing or not-yet-due KPIs
                  are excluded and remaining weights rescaled — never treated as
                  zero.
                </p>
                {data.no_source_kpis.length > 0 && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    <strong>
                      {data.no_source_kpis.length} KPIs have no source
                    </strong>{" "}
                    ({data.no_source_kpis.map(label).join(", ")}). They are
                    excluded from every score until a source is connected.{" "}
                    <Link
                      href="/knowledge"
                      className="underline hover:text-foreground"
                    >
                      Connections
                    </Link>
                  </p>
                )}
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={null}>
      <Dashboard />
    </Suspense>
  );
}
