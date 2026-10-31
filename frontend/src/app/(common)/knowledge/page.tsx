"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { Box, FileText, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, Loading, PageHeader } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, API_URL, getClaims, getToken } from "@/lib/api";
import { fmt, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { DocumentDetail, DocumentRow, KpiCatalog } from "@/lib/types";

const ACCEPT = ".pdf,.doc,.docx,.xls,.xlsx,.csv,.md,.txt";
const size = (n: number) => (n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB");

export default function KnowledgePage() {
  const docs = useApi<DocumentRow[]>("/documents");

  return (
    <div className="space-y-4">
      <PageHeader
        title="Knowledge"
        subtitle="Everything here is read by the Copilot when it answers questions about your company."
      />

      <Tabs defaultValue="documents">
        <TabsList>
          <TabsTrigger value="documents">
            Company documents
            {docs.data && (
              <span className="ml-1.5 rounded-md bg-muted px-1.5 text-xs tabular-nums">{docs.data.length}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="advanced">Advanced</TabsTrigger>
        </TabsList>
        <TabsContent value="documents" className="mt-6">
          <Documents {...docs} />
        </TabsContent>
        <TabsContent value="advanced" className="mt-6">
          <Advanced />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Documents({ data, error, loading, reload }: ReturnType<typeof useApi<DocumentRow[]>>) {
  const picker = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [viewing, setViewing] = useState<DocumentDetail | null>(null);
  const me = getClaims();
  const canEdit = me?.role === "admin" || me?.role === "editor";

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    let added = 0;
    for (const f of Array.from(files)) {
      const body = new FormData();
      body.append("file", f);
      body.append("title", f.name);
      try {
        // multipart: the shared api() helper always sets a JSON content type, so this one posts directly.
        const res = await fetch(`${API_URL}/documents`, {
          method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body,
        });
        if (!res.ok) throw new Error((await res.json()).detail ?? "Upload failed");
        added++;
      } catch (err) {
        toast.error(`${f.name}: ${err instanceof Error ? err.message : "Upload failed"}`);
      }
    }
    if (added) toast.success(`Added ${added} document${added === 1 ? "" : "s"}.`);
    if (picker.current) picker.current.value = "";
    setBusy(false);
    reload();
  }

  async function view(d: DocumentRow) {
    try {
      setViewing(await api<DocumentDetail>(`/documents/${d.id}`));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not open document");
    }
  }

  async function remove(d: DocumentRow) {
    if (!window.confirm(`Delete "${d.title}"?`)) return;
    try {
      await api(`/documents/${d.id}`, { method: "DELETE" });
      toast.success("Deleted.");
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">Your own files, plus the built-in reference playbooks.</p>
        {canEdit && (
          <Button onClick={() => picker.current?.click()} disabled={busy}>
            <Plus />{busy ? "Uploading…" : "Add documents"}
          </Button>
        )}
        <input ref={picker} type="file" multiple accept={ACCEPT} className="hidden"
          onChange={(e) => upload(e.target.files)} />
      </div>

      {canEdit && (
        <div
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}
          onClick={() => picker.current?.click()}
          className={`cursor-pointer rounded-xl border border-dashed p-6 text-center transition-colors ${
            over ? "border-primary bg-primary/5" : "hover:bg-muted/30"}`}>
          <p className="text-sm text-muted-foreground">Drop files here to add them</p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            PDF, Word, Excel, CSV, Markdown or text, up to 50 MB each
          </p>
        </div>
      )}

      <Loading error={error} loading={loading && !data} />
      {data?.length === 0 && <p className="text-sm text-muted-foreground">No documents yet.</p>}
      {!!data?.length && (
        <ul className="divide-y overflow-hidden rounded-xl border">
          {data.map((d) => (
            <li key={d.id} className="flex items-center gap-4 px-4 py-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                <FileText className="size-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold">{d.title}</span>
                  {d.domain !== "general" && <Badge variant="secondary" className="uppercase">{d.domain}</Badge>}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="size-1.5 rounded-full bg-muted-foreground" />
                  {d.builtin ? "Built in" : "Uploaded"} · Added {day(d.created_at)} · {size(d.size_bytes)}
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => view(d)}>View</Button>
              {canEdit && !d.builtin ? (
                <DropdownMenu>
                  <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" />}>
                    <MoreHorizontal /><span className="sr-only">More</span>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-40">
                    <DropdownMenuItem variant="destructive" onClick={() => remove(d)}>
                      <Trash2 />Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : <span className="w-8" />}
            </li>
          ))}
        </ul>
      )}

      <Dialog open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{viewing?.title}</DialogTitle>
            <DialogDescription>
              {viewing && `${viewing.chunk_count} indexed passages · ${size(viewing.size_bytes)}`}
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[65vh] overflow-y-auto whitespace-pre-wrap text-sm text-muted-foreground">
            {viewing?.text}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const ENTRY = [
  { href: "/documents", icon: FileText, title: "Document search",
    body: "Search every passage the Copilot can cite." },
  { href: "/memory", icon: Box, title: "Memory store",
    body: "What the Copilot remembers from your earlier sessions." },
];

function Advanced() {
  const { data, error, loading } = useApi<KpiCatalog>("/kpis");

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2">
        {ENTRY.map((e) => (
          <Link key={e.href} href={e.href}
            className="rounded-xl border p-4 transition-colors hover:bg-muted/50">
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
