"use client";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { api, clearToken, getClaims, getToken } from "@/lib/api";
import { readSse } from "@/lib/sse";
import type { LiveAlert, UnreadSummary } from "@/lib/types";
import { currentPeriod } from "@/lib/format";

type NavItem = { href: string; label: string; badge?: "alerts" | "approvals_pending" };
const NAV: { heading: string; items: NavItem[] }[] = [
  { heading: "Work", items: [
    { href: "/", label: "Dashboard" }, { href: "/unread", label: "Unread", badge: "alerts" },
    { href: "/reports", label: "Reports" }, { href: "/copilot", label: "Ask Copilot" },
    { href: "/sessions", label: "Sessions" }, { href: "/memories", label: "Memories" }, { href: "/pinned", label: "Pinned" } ] },
  { heading: "Build", items: [
    { href: "/skills", label: "Skills" }, { href: "/agents", label: "Agents" }, { href: "/documents", label: "Documents" } ] },
  { heading: "Admin", items: [
    { href: "/inputs", label: "Manual inputs" }, { href: "/approvals", label: "Approvals", badge: "approvals_pending" },
    { href: "/connections", label: "Connections" }, { href: "/settings/scorecard", label: "Scorecard rules" },
    { href: "/settings/schedules", label: "Schedules" } ] },
];

export function usePeriod() {
  // Pages render only after AppShell mounts on the client, so reading localStorage here is safe.
  const [period, setPeriod] = useState(() => localStorage.getItem("chro_period") ?? currentPeriod());
  return [period, (p: string) => { localStorage.setItem("chro_period", p); setPeriod(p); }] as const;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const hasToken = useSyncExternalStore(
    () => () => {},
    () => !!getToken(),
    () => false,
  );
  const ready = hasToken;
  const me = hasToken ? getClaims() : null;
  const [counts, setCounts] = useState<UnreadSummary>({ alerts: 0, approvals_pending: 0 });
  useEffect(() => {
    if (!hasToken || path === "/login") return;
    let live = true;
    const load = () => api<UnreadSummary>("/unread/summary").then((c) => live && setCounts(c)).catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => { live = false; clearInterval(t); };
  }, [hasToken, path]);
  const [toasts, setToasts] = useState<(LiveAlert & { key: number })[]>([]);
  const onLogin = path === "/login";
  useEffect(() => {
    if (!hasToken || onLogin) return;
    // Live alerts: one stream per signed-in tab, reconnecting with backoff if it drops.
    const ac = new AbortController();
    let live = true;
    const refresh = () => api<UnreadSummary>("/unread/summary").then((c) => live && setCounts(c)).catch(() => {});
    (async () => {
      let delay = 1000;
      while (live) {
        try {
          await readSse("/alerts/stream", (name, data) => {
            if (name !== "alert") return;
            const a = data as LiveAlert;
            refresh();
            const key = Date.now() + a.id;
            setToasts((t) => [...t.slice(-3), { ...a, key }]);
            setTimeout(() => live && setToasts((t) => t.filter((x) => x.key !== key)), 10_000);
          }, ac.signal);
          delay = 1000;
        } catch { /* dropped or refused: retry below */ }
        if (!live) break;
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, 30_000);
      }
    })();
    return () => { live = false; ac.abort(); };
  }, [hasToken, onLogin]);
  useEffect(() => {
    // Read storage directly: `hasToken` is the server value (false) during hydration, so using it here
    // would bounce a signed-in user to /login on every hard reload.
    if (path !== "/login" && !getToken()) router.replace("/login");
  }, [path, router]);

  if (path === "/login") return <>{children}</>;
  if (!ready) return null;
  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 overflow-y-auto border-r border-slate-200 bg-white p-4">
        <div className="mb-5 font-semibold">CHRO Copilot</div>
        <nav className="space-y-4" aria-label="Main">
          {NAV.map((g) => (
            <div key={g.heading}>
              <div className="mb-1 px-3 text-xs font-medium uppercase tracking-wide text-slate-400">{g.heading}</div>
              <div className="space-y-0.5">
                {g.items.map((n) => {
                  const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
                  return (
                    <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                      className={`block rounded px-3 py-1.5 text-sm ${active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}>
                      {n.label}
                      {n.badge && counts[n.badge] > 0 && (
                        <span className="ml-2 rounded-full bg-red-600 px-1.5 text-xs text-white" aria-label={`${counts[n.badge]} unread`}>{counts[n.badge]}</span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        {me && <p className="mt-6 px-3 text-xs text-slate-500">Signed in as <strong>{me.sub}</strong> ({me.role})</p>}
        <button className="mt-8 text-xs text-slate-500 underline"
          onClick={() => { clearToken(); router.replace("/login"); }}>Sign out</button>
      </aside>
      <main className="min-w-0 flex-1 p-6">{children}</main>
      <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 w-80 space-y-2">
        {toasts.map((t) => (
          <Link key={t.key} href="/unread" onClick={() => setToasts((all) => all.filter((x) => x.key !== t.key))}
            className="pointer-events-auto block rounded-lg border border-slate-300 bg-white p-3 text-sm shadow-lg hover:bg-slate-50">
            <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${t.severity === "urgent" || t.severity === "high" ? "bg-red-100 text-red-900" : "bg-amber-100 text-amber-900"}`}>{t.severity}</span>
            {t.title}
          </Link>
        ))}
      </div>
    </div>
  );
}
