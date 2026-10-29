"use client";
import { useState } from "react";
import { Card, Loading } from "@/components/ui";
import { API_URL, api, getClaims, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Doc { id: number; title: string; filename: string; domain: string; builtin: boolean; chunk_count: number; uploaded_by: string; created_at: string }
interface Hit { document_id: number; title: string; domain: string; chunk: number; snippet: string; score: number }
const DOMAINS = ["general", "hr", "legal", "policy", "finance", "operations", "scorecard"];

/** Render FTS5 snippets: the engine marks matches as [word]. Everything else is plain text (never HTML). */
function Snippet({ text }: { text: string }) {
  return <>{text.split(/(\[[^\]]+\])/).map((p, i) => /^\[[^\]]+\]$/.test(p) ? <mark key={i} className="bg-yellow-100">{p.slice(1, -1)}</mark> : <span key={i}>{p}</span>)}</>;
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

  const input = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";
  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold">Documents</h1>
      <p className="text-sm text-slate-600">Policy and reference documents the Copilot can search and cite. Built-in documents describe every KPI and how scores are calculated. Text, Markdown, PDF and Word files up to 10 MB.</p>

      <Card title="Search">
        <form onSubmit={(e) => { e.preventDefault(); setSubmitted(q.trim()); }} className="flex gap-2">
          <input aria-label="Search documents" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. regrettable exits, probation, notice period" className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm" />
          <button className="rounded bg-slate-900 px-4 py-2 text-sm text-white">Search</button>
        </form>
        {submitted && <Loading error={hits.error} loading={hits.loading} />}
        <ul className="mt-3 space-y-3 text-sm">
          {hits.data?.map((h, i) => (
            <li key={i}><div className="font-medium">{h.title} <span className="text-xs font-normal text-slate-500">· passage {h.chunk + 1} · {h.domain}</span></div>
              <div className="text-slate-700"><Snippet text={h.snippet} /></div></li>))}
          {submitted && hits.data?.length === 0 && <li className="text-slate-500">No matches.</li>}
        </ul>
      </Card>

      {canEdit && (
        <Card title="Upload a document">
          <form onSubmit={upload} className="space-y-3 text-sm">
            <label className="block">File<input required type="file" accept=".txt,.md,.markdown,.pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className={input} /></label>
            <div className="grid grid-cols-2 gap-3">
              <label>Title (optional)<input value={title} onChange={(e) => setTitle(e.target.value)} className={input} /></label>
              <label>Topic<select value={domain} onChange={(e) => setDomain(e.target.value)} className={input}>{DOMAINS.map((d) => <option key={d}>{d}</option>)}</select></label>
            </div>
            {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-emerald-700" : "text-red-700"}>{msg.text}</p>}
            <button className="rounded bg-slate-900 px-3 py-1.5 text-white">Upload</button>
          </form>
        </Card>
      )}

      <Card title={`Library (${docs.data?.length ?? 0})`}>
        <Loading error={docs.error} loading={docs.loading && !docs.data} />
        <ul className="divide-y divide-slate-100 text-sm">
          {docs.data?.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3 py-2">
              <span><strong>{d.title}</strong> <span className="text-xs text-slate-500">{d.builtin ? "built in" : `${d.filename} · ${d.uploaded_by}`} · {d.chunk_count} passage{d.chunk_count === 1 ? "" : "s"} · {d.domain}</span></span>
              {canEdit && !d.builtin && <button className="text-xs text-red-800 underline" onClick={async () => { if (window.confirm(`Delete “${d.title}”?`)) { await api(`/documents/${d.id}`, { method: "DELETE" }); docs.reload(); hits.reload(); } }}>Delete</button>}
            </li>))}
        </ul>
      </Card>
    </div>
  );
}
