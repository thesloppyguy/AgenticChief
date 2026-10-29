"use client";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, Loading } from "@/components/ui";
import { API_URL, api, getClaims, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Doc { id: number; title: string; filename: string; domain: string; builtin: boolean; chunk_count: number; uploaded_by: string; created_at: string }
interface Hit { document_id: number; title: string; domain: string; chunk: number; snippet: string; score: number }
const DOMAINS = ["general", "hr", "legal", "policy", "finance", "operations", "scorecard"];

/** Render FTS5 snippets: the engine marks matches as [word]. Everything else is plain text (never HTML). */
function Snippet({ text }: { text: string }) {
  return <>{text.split(/(\[[^\]]+\])/).map((p, i) => /^\[[^\]]+\]$/.test(p) ? <mark key={i} className="bg-warning/20 text-foreground">{p.slice(1, -1)}</mark> : <span key={i}>{p}</span>)}</>;
}

export default function Documents() {
  const me = getClaims();
  const canEdit = me?.role === "admin" || me?.role === "editor";
  const docs = useApi<Doc[]>("/documents");
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const hits = useApi<Hit[]>(submitted ? `/documents/search?q=${encodeURIComponent(submitted)}&limit=8` : null);
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState("general");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setMsg(null);
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("domain", domain);
    const res = await fetch(`${API_URL}/documents`, { method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: form });
    if (res.ok) { setMsg({ ok: true, text: "Uploaded and indexed." }); setFile(null); setTitle(""); (e.target as HTMLFormElement).reset(); docs.reload(); }
    else { let d = "Upload failed"; try { d = (await res.json()).detail ?? d; } catch {} setMsg({ ok: false, text: d }); }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Documents</h1>
      <p className="text-sm text-muted-foreground">Policy and reference documents the Copilot can search and cite. Built-in documents describe every KPI and how scores are calculated. Text, Markdown, PDF and Word files up to 10 MB.</p>

      <Card title="Search">
        <form onSubmit={(e) => { e.preventDefault(); setSubmitted(q.trim()); }} className="flex gap-2">
          <Input aria-label="Search documents" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. regrettable exits, probation, notice period" className="flex-1" />
          <Button type="submit">Search</Button>
        </form>
        {submitted && <Loading error={hits.error} loading={hits.loading} />}
        <ul className="mt-3 space-y-3 text-sm">
          {hits.data?.map((h, i) => (
            <li key={i}><div className="font-medium">{h.title} <span className="text-xs font-normal text-muted-foreground">· passage {h.chunk + 1} · {h.domain}</span></div>
              <div className="text-foreground/80"><Snippet text={h.snippet} /></div></li>))}
          {submitted && hits.data?.length === 0 && <li className="text-muted-foreground">No matches.</li>}
        </ul>
      </Card>

      {canEdit && (
        <Card title="Upload a document">
          <form onSubmit={upload} className="space-y-3 text-sm">
            <div className="space-y-1">
              <Label htmlFor="doc-file">File</Label>
              <Input id="doc-file" required type="file" accept=".txt,.md,.markdown,.pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="doc-title">Title (optional)</Label>
                <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="doc-domain">Topic</Label>
                <Select value={domain} onValueChange={(v) => { if (v) setDomain(v); }}>
                  <SelectTrigger id="doc-domain" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>{DOMAINS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            {msg && <Alert variant={msg.ok ? "default" : "destructive"} role={msg.ok ? "status" : "alert"}><AlertDescription className={msg.ok ? "text-success" : undefined}>{msg.text}</AlertDescription></Alert>}
            <Button type="submit">Upload</Button>
          </form>
        </Card>
      )}

      <Card title={`Library (${docs.data?.length ?? 0})`}>
        <Loading error={docs.error} loading={docs.loading && !docs.data} />
        <ul className="divide-y divide-border text-sm">
          {docs.data?.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3 py-2">
              <span><strong>{d.title}</strong> <span className="text-xs text-muted-foreground">{d.builtin ? "built in" : `${d.filename} · ${d.uploaded_by}`} · {d.chunk_count} passage{d.chunk_count === 1 ? "" : "s"} · {d.domain}</span></span>
              {canEdit && !d.builtin && <Button variant="ghost" size="xs" className="text-destructive" onClick={async () => { if (window.confirm(`Delete “${d.title}”?`)) { await api(`/documents/${d.id}`, { method: "DELETE" }); docs.reload(); hits.reload(); } }}>Delete</Button>}
            </li>))}
        </ul>
      </Card>
    </div>
  );
}
