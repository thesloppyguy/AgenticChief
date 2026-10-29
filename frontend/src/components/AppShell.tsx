"use client";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { api, getToken, subscribeToken } from "@/lib/api";
import { readSse } from "@/lib/sse";
import type { LiveAlert, UnreadSummary } from "@/lib/types";
import { currentPeriod } from "@/lib/format";
import { toast } from "sonner";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/shared/app-sidebar";
import { SettingsDialog } from "@/components/shared/settings-dialog";

export function usePeriod() {
  // Pages render only after AppShell mounts on the client, so reading localStorage here is safe.
  const [period, setPeriod] = useState(
    () => localStorage.getItem("chro_period") ?? currentPeriod(),
  );
  return [
    period,
    (p: string) => {
      localStorage.setItem("chro_period", p);
      setPeriod(p);
    },
  ] as const;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const router = useRouter();
  const hasToken = useSyncExternalStore(
    subscribeToken,
    () => !!getToken(),
    () => false,
  );
  const ready = hasToken;
  const onLogin = path === "/login";
  const [counts, setCounts] = useState<UnreadSummary>({
    alerts: 0,
    approvals_pending: 0,
  });
  useEffect(() => {
    if (!hasToken || onLogin) return;
    let live = true;
    const load = () =>
      api<UnreadSummary>("/unread/summary")
        .then((c) => live && setCounts(c))
        .catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [hasToken, onLogin]);
  useEffect(() => {
    if (!hasToken || onLogin) return;
    // Live alerts: one stream per signed-in tab, reconnecting with backoff if it drops.
    const ac = new AbortController();
    let live = true;
    const refresh = () =>
      api<UnreadSummary>("/unread/summary")
        .then((c) => live && setCounts(c))
        .catch(() => {});
    void (async () => {
      let delay = 1000;
      while (live && !ac.signal.aborted) {
        try {
          await readSse(
            "/alerts/stream",
            (name, data) => {
              if (name !== "alert") return;
              const a = data as LiveAlert;
              refresh();
              const urgent = a.severity === "urgent" || a.severity === "high";
              (urgent ? toast.error : toast.warning)(a.title, {
                description: a.severity,
                duration: 10_000,
                action: {
                  label: "View",
                  onClick: () => router.push("/unread"),
                },
              });
            },
            ac.signal,
          );
          delay = 1000;
        } catch {
          /* dropped or refused: retry below */
        }
        if (!live || ac.signal.aborted) break;
        await new Promise<void>((resolve) => {
          const t = setTimeout(resolve, delay);
          ac.signal.addEventListener("abort", () => {
            clearTimeout(t);
            resolve();
          }, { once: true });
        });
        delay = Math.min(delay * 2, 30_000);
      }
    })().catch(() => {});
    return () => {
      live = false;
      ac.abort();
    };
  }, [hasToken, onLogin, router]);
  useEffect(() => {
    // Read storage directly: `hasToken` is the server value (false) during hydration, so using it here
    // would bounce a signed-in user to /login on every hard reload.
    if (path !== "/login" && !getToken()) router.replace("/login");
  }, [path, router]);

  // Always render `{children}` so Cache Components can validate route segments.
  // Returning null here drops layouts/pages from the tree (instant-unrendered-segment).
  if (onLogin || !ready) return <>{children}</>;

  return (
    <>
      <SidebarProvider>
        <AppSidebar open={open} onOpenChange={setOpen} />
        <SidebarInset>
          <header className="flex h-16 shrink-0 items-center gap-2">
            <div className="flex items-center gap-2 px-4">
              <SidebarTrigger className="-ml-1" />
            </div>
          </header>
          <div className="flex flex-1 flex-col gap-4 p-4 pt-0">{children}</div>
        </SidebarInset>
      </SidebarProvider>
      <SettingsDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
