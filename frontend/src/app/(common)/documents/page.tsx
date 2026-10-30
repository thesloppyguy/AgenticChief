"use client";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { api, API_URL, getClaims, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { DocumentHit, DocumentRow } from "@/lib/types";

const kb = (n: number) => `${Math.max(1, Math.round(n / 1024))} KB`;

export default function DocumentsPage() {
  const { data, error, loading, reload } = useApi<DocumentRow[]>("/documents");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<DocumentHit[] | null>(null);
  const [busy, setBusy] = useState(false);
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
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
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
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Reference material the Copilot can search and cite. Document text is treated as data to quote,
          never as instructions to follow.
        </p>
      </div>

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
            <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{d.title}</span>
                  {d.builtin && <Badge variant="secondary">Built in</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {d.filename} · {kb(d.size_bytes)} · {d.chunk_count} passages · {d.uploaded_by}
                </div>
              </div>
              {canEdit && !d.builtin && (
                <Button variant="ghost" size="sm" className="text-destructive"
                  onClick={() => remove(d)}>Delete</Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {canEdit && (
        <Card title="Upload">
          <form onSubmit={upload}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="file">File (PDF, Word, text or Markdown)</FieldLabel>
                <input id="file" ref={file} type="file" className="text-sm" />
              </Field>
              <Field>
                <FieldLabel htmlFor="title">Title (optional)</FieldLabel>
                <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)}
                  placeholder="Defaults to the file name" />
              </Field>
              <Button type="submit" disabled={busy}>{busy ? "Uploading…" : "Upload"}</Button>
            </FieldGroup>
          </form>
        </Card>
      )}
    </div>
  );
}
