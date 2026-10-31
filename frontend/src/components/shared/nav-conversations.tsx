"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, MessageSquare } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { isRouteActive } from "@/components/shared/nav-utils";
import { api } from "@/lib/api";
import { SESSIONS_CHANGED, type SessionPage, type SessionRow } from "@/lib/types";

const PAGE = 20;

export function NavConversations() {
  const pathname = usePathname();
  const [items, setItems] = useState<SessionRow[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const sentinel = useRef<HTMLDivElement>(null);
  const loadingMore = useRef(false);

  const load = useCallback(async (next: string | null, append: boolean) => {
    if (append && loadingMore.current) return;
    loadingMore.current = true;
    try {
      const qs = new URLSearchParams({ limit: String(PAGE) });
      if (next) qs.set("cursor", next);
      const page = await api<SessionPage>(`/copilot/sessions?${qs}`);
      setItems((prev) => (append ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setDone(!page.next_cursor);
    } catch {
      setDone(true);
    } finally {
      setLoading(false);
      loadingMore.current = false;
    }
  }, []);

  // Initial load and full refresh (new session created elsewhere).
  useEffect(() => {
    setLoading(true);
    setDone(false);
    setCursor(null);
    loadingMore.current = false;
    void load(null, false);
  }, [load, tick]);

  useEffect(() => {
    const onChange = () => setTick((t) => t + 1);
    window.addEventListener(SESSIONS_CHANGED, onChange);
    return () => window.removeEventListener(SESSIONS_CHANGED, onChange);
  }, []);

  // Infinite scroll: when the sentinel enters the sidebar's scrollport, fetch the next page.
  useEffect(() => {
    const el = sentinel.current;
    if (!el || done || loading) return;
    const root = el.closest("[data-slot=sidebar-content]");
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting && cursor && !loadingMore.current) {
          void load(cursor, true);
        }
      },
      { root: root instanceof Element ? root : null, rootMargin: "80px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [cursor, done, loading, load, items.length]);

  return (
    <Collapsible defaultOpen className="group/collapsible">
      <SidebarGroup className="group-data-[collapsible=icon]:hidden">
        <SidebarGroupLabel
          render={<CollapsibleTrigger />}
          className="cursor-pointer"
        >
          Conversations
          <ChevronRight className="ml-auto transition-transform group-data-open/collapsible:rotate-90" />
        </SidebarGroupLabel>
        <CollapsibleContent>
          <SidebarMenu>
            {items.map((s) => {
              const url = `/chat/${s.id}`;
              return (
                <SidebarMenuItem key={s.id}>
                  <SidebarMenuButton
                    render={<Link href={url} prefetch />}
                    isActive={isRouteActive(pathname, url)}
                    tooltip={s.title}
                  >
                    <MessageSquare />
                    <span className="truncate">{s.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
            {!loading && items.length === 0 && (
              <SidebarMenuItem>
                <SidebarMenuButton disabled className="text-sidebar-foreground/70">
                  <span>No conversations yet</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
            {!done && (
              <div ref={sentinel} className="h-1 w-full" aria-hidden />
            )}
            {loading && items.length > 0 && (
              <SidebarMenuItem>
                <SidebarMenuButton disabled className="text-sidebar-foreground/70">
                  <span>Loading…</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
          </SidebarMenu>
        </CollapsibleContent>
      </SidebarGroup>
    </Collapsible>
  );
}
