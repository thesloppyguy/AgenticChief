"use client";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { api, clearToken, getClaims, getToken } from "@/lib/api";
import { readSse } from "@/lib/sse";
import type { LiveAlert, UnreadSummary } from "@/lib/types";
import { currentPeriod } from "@/lib/format";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import { LogOut, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader,
  SidebarInset, SidebarMenu, SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger,
} from "@/components/ui/sidebar";

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
  const { resolvedTheme, setTheme } = useTheme();
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
            const urgent = a.severity === "urgent" || a.severity === "high";
            (urgent ? toast.error : toast.warning)(a.title, {
              description: a.severity, duration: 10_000,
              action: { label: "View", onClick: () => router.push("/unread") },
            });
          }, ac.signal);
          delay = 1000;
        } catch { /* dropped or refused: retry below */ }
        if (!live) break;
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, 30_000);
      }
    })();
    return () => { live = false; ac.abort(); };
  }, [hasToken, onLogin, router]);
  useEffect(() => {
    // Read storage directly: `hasToken` is the server value (false) during hydration, so using it here
    // would bounce a signed-in user to /login on every hard reload.
    if (path !== "/login" && !getToken()) router.replace("/login");
  }, [path, router]);

  if (path === "/login") return <>{children}</>;
  if (!ready) return null;
  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader className="px-4 py-3 font-semibold">CHRO Copilot</SidebarHeader>
        <SidebarContent>
          {NAV.map((g) => (
            <SidebarGroup key={g.heading}>
              <SidebarGroupLabel>{g.heading}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {g.items.map((n) => {
                    const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
                    const count = n.badge ? counts[n.badge] : 0;
                    return (
                      <SidebarMenuItem key={n.href}>
                        <SidebarMenuButton isActive={active} render={<Link href={n.href} aria-current={active ? "page" : undefined} />}>
                          {n.label}
                        </SidebarMenuButton>
                        {count > 0 && <SidebarMenuBadge aria-label={`${count} unread`}>{count}</SidebarMenuBadge>}
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </SidebarContent>
        <SidebarFooter className="gap-2 p-4">
          {me && <p className="text-xs text-muted-foreground">Signed in as <strong>{me.sub}</strong> ({me.role})</p>}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="flex-1"
              onClick={() => { clearToken(); router.replace("/login"); }}><LogOut />Sign out</Button>
            <Button variant="outline" size="icon-sm" aria-label="Toggle theme"
              onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
              <Sun className="dark:hidden" /><Moon className="hidden dark:block" />
            </Button>
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="min-w-0">
        <header className="flex h-12 items-center border-b px-4 md:hidden"><SidebarTrigger /></header>
        <div className="p-6">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
