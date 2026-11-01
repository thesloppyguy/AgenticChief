"use client";
import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { toast } from "sonner";
import { Card, Loading, PageHeader } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, API_URL, getClaims, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { DocumentDetail, DocumentHit, DocumentRow } from "@/lib/types";

const ACCEPT = ".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.md,.txt,.markdown";
const kb = (n: number) => `${Math.max(1, Math.round(n / 1024))} KB`;

function extOf(name: string) {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

function isTabular(filename: string) {
  return [".csv", ".xlsx", ".xls"].includes(extOf(filename));
}

/** Split TSV-ish indexed text into table rows for spreadsheet/CSV previews. */
function tabularRows(text: string): string[][] {
  const lines = text.split("\n").filter((l) => l.trim() && !l.startsWith("## ") && !l.startsWith("… "));
  return lines.slice(0, 200).map((line) => line.split("\t"));
}

export default function DocumentsPage() {
  const { data, error, loading, reload } = useApi<DocumentRow[]>("/documents");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<DocumentHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [viewing, setViewing] = useState<DocumentDetail | null>(null);
  const [opening, setOpening] = useState(false);
  const [title, setTitle] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const me = getClaims();
  const canEdit = me?.role === "admin" || me?.role === "editor";

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return setHits(null);
    try {
      setHits(await api<DocumentHit[]>(`/documents/search?q=${encodeURIComponent(q)}`));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search failed");
    }
  }

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    const picked = file.current?.files?.[0];
    if (!picked) return toast.error("Choose a file first.");
    setBusy(true);
    const body = new FormData();
    body.append("file", picked);
    body.append("title", title || picked.name);
    try {
      // multipart: the shared api() helper always sets a JSON content type, so this one posts directly.
      const res = await fetch(`${API_URL}/documents`, {
        method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body,
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Upload failed");
      toast.success("Uploaded and indexed.");
      setTitle("");
      if (file.current) file.current.value = "";
      setUploadOpen(false);
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function openDoc(d: DocumentRow) {
    setOpening(true);
    try {
      setViewing(await api<DocumentDetail>(`/documents/${d.id}`));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not open document");
    } finally {
      setOpening(false);
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

  const table = viewing && isTabular(viewing.filename) ? tabularRows(viewing.text) : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Knowledge"
        subtitle="Reference material the Copilot can search and cite. Document text is treated as data to quote, never as instructions to follow."
        actions={
          canEdit ? (
            <Button className="rounded-full" onClick={() => setUploadOpen(true)}>
              <Upload />
              Upload
            </Button>
          ) : undefined
        }
      />

      <form onSubmit={search}>
        <InputGroup>
          <InputGroupInput placeholder="Search every document…" value={q}
            onChange={(e) => setQ(e.target.value)} />
          <InputGroupAddon align="inline-end">
            <InputGroupButton type="submit" size="xs">Search</InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </form>

      {hits && (
        <Card title={`${hits.length} passage${hits.length === 1 ? "" : "s"}`}
          action={<Button variant="ghost" size="sm" onClick={() => { setHits(null); setQ(""); }}>Clear</Button>}>
          {hits.length === 0 && <p className="text-sm text-muted-foreground">Nothing matched.</p>}
          <ul className="space-y-3">
            {hits.map((h, i) => (
              <li key={i} className="text-sm">
                <div className="font-medium">{h.title}</div>
                <p className="mt-1 text-muted-foreground">{h.snippet}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Library">
        <Loading error={error} loading={loading && !data} />
        {data?.length === 0 && <p className="text-sm text-muted-foreground">No documents yet.</p>}
        <ul className="divide-y">
          {data?.map((d) => (
            <li
              key={d.id}
              className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
            >
              <button
                type="button"
                disabled={opening}
                onClick={() => openDoc(d)}
                className="min-w-0 flex-1 rounded-lg px-1 py-0.5 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
              >
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{d.title}</span>
                  {d.builtin && <Badge variant="secondary">Built in</Badge>}
                  <Badge variant="outline" className="font-normal uppercase">
                    {extOf(d.filename).replace(".", "") || "file"}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  {d.filename} · {kb(d.size_bytes)} · {d.chunk_count} passages · {d.uploaded_by}
                </div>
              </button>
              {canEdit && !d.builtin && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={() => remove(d)}
                >
                  Delete
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Dialog open={!!viewing} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
          <DialogHeader className="shrink-0 border-b px-5 py-4">
            <DialogTitle>{viewing?.title}</DialogTitle>
            <DialogDescription>
              {viewing &&
                `${viewing.filename} · ${viewing.chunk_count} passages · ${kb(viewing.size_bytes)} · indexed text preview`}
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {table && table.length > 0 ? (
              <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {table[0].map((cell, i) => (
                        <TableHead key={i} className="whitespace-nowrap">
                          {cell || `Col ${i + 1}`}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {table.slice(1).map((row, ri) => (
                      <TableRow key={ri}>
                        {table[0].map((_, ci) => (
                          <TableCell key={ci} className="max-w-[16rem] truncate whitespace-nowrap text-xs">
                            {row[ci] ?? ""}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-foreground">
                {viewing?.text || "No text extracted."}
              </pre>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={uploadOpen}
        onOpenChange={(open) => {
          setUploadOpen(open);
          if (!open) {
            setTitle("");
            if (file.current) file.current.value = "";
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Upload document</DialogTitle>
            <DialogDescription>
              PDF, Word, PowerPoint, Excel, CSV, Markdown, or text. Indexed for search and citation.
            </DialogDescription>
          </DialogHeader>
          <form id="document-upload" onSubmit={upload}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="file">File</FieldLabel>
                <input id="file" ref={file} type="file" accept={ACCEPT} className="text-sm" />
              </Field>
              <Field>
                <FieldLabel htmlFor="title">Title (optional)</FieldLabel>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Defaults to the file name"
                />
              </Field>
            </FieldGroup>
          </form>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setUploadOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" form="document-upload" disabled={busy}>
              {busy ? "Uploading…" : "Upload"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
