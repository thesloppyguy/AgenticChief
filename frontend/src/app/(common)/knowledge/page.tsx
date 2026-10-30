"use client";
import Link from "next/link";
import { Box, FileText } from "lucide-react";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { fmt, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { KpiCatalog } from "@/lib/types";

const ENTRY = [
  { href: "/documents", icon: FileText, title: "Documents",
    body: "Policies and reference material the Copilot can search and cite." },
  { href: "/memory", icon: Box, title: "Memory store",
    body: "What the Copilot remembers from your earlier sessions." },
];

export default function KnowledgePage() {
  const { data, error, loading } = useApi<KpiCatalog>("/kpis");

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Knowledge</h1>
        <p className="text-sm text-muted-foreground">
          What the platform knows: the KPI register that defines every score, plus the documents and
          memories the Copilot draws on.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {ENTRY.map((e) => (
          <Link key={e.href} href={e.href}
            className="rounded-lg border p-4 transition-colors hover:bg-muted/50">
            <div className="flex items-center gap-2 font-medium">
              <e.icon className="size-4 text-muted-foreground" />{e.title}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{e.body}</p>
          </Link>
        ))}
      </div>

      <Card title="KPI register">
        <Loading error={error} loading={loading && !data} />
        {data && (
          <>
            <p className="mb-3 text-sm text-muted-foreground">
              7 pillars, {data.kpis.length} sub-KPIs. A KPI marked <em>Manual</em> is entered by an
              editor each month; the rest are pulled from a source system.
            </p>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>KPI</TableHead>
                    <TableHead>Pillar</TableHead>
                    <TableHead className="text-right">Weight in pillar</TableHead>
                    <TableHead className="text-right">Target</TableHead>
                    <TableHead>Direction</TableHead>
                    <TableHead>Source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.kpis.map((k) => (
                    <TableRow key={k.key}>
                      <TableCell className="font-medium">{label(k.key)}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {label(k.pillar)}
                        <span className="ml-1 text-xs tabular-nums">
                          ({Math.round((data.pillar_weights[k.pillar] ?? 0) * 100)}%)
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {Math.round(k.weight * 100)}%
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{fmt(k.target)}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">
                        {k.direction === "lower" ? "Lower is better" : "Higher is better"}
                      </TableCell>
                      <TableCell>
                        {k.manual
                          ? <Badge variant="secondary">Manual</Badge>
                          : <span className="text-xs text-muted-foreground">Sourced</span>}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
