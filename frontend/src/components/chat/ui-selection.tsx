"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";
import { currentPeriod } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCopilotPanel } from "./copilot-panel-context";

const PERIOD_KEY = "chro_period";

export type UiSelection = {
  type: string;
  id: string;
  label: string;
  route: string;
  period: string;
  refs?: {
    company_id?: number;
    company_code?: string;
    pillar?: string;
    kpi_key?: string;
    approval_id?: number;
    brief_id?: number;
    pulse_key?: string;
    issue_rank?: number;
  };
  dataSnapshot?: Record<string, unknown>;
};

/** Live map of instrumented surfaces → selection payload (for the page-wide picker). */
const surfaceRegistry = new Map<string, UiSelection>();

type UiSelectionContextValue = {
  selection: UiSelection | null;
  setSelection: (sel: UiSelection | null) => void;
  clearSelection: () => void;
  pick: (sel: UiSelection) => void;
};

const UiSelectionContext = createContext<UiSelectionContextValue | null>(null);

export function UiSelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<UiSelection | null>(null);
  const { setOpen, setSelectMode } = useCopilotPanel();

  const clearSelection = useCallback(() => setSelection(null), []);

  const pick = useCallback(
    (sel: UiSelection) => {
      setSelection(sel);
      setOpen(true);
      setSelectMode(false);
    },
    [setOpen, setSelectMode],
  );

  const value = useMemo(
    () => ({ selection, setSelection, clearSelection, pick }),
    [selection, clearSelection, pick],
  );

  return (
    <UiSelectionContext.Provider value={value}>
      {children}
      <SelectModeLayer />
    </UiSelectionContext.Provider>
  );
}

export function useUiSelection() {
  const ctx = useContext(UiSelectionContext);
  if (!ctx) {
    throw new Error("useUiSelection must be used within UiSelectionProvider");
  }
  return ctx;
}

/** Optional: pages outside the provider can no-op safely. */
export function useUiSelectionOptional() {
  return useContext(UiSelectionContext);
}

function readPeriod() {
  if (typeof window === "undefined") return currentPeriod();
  return localStorage.getItem(PERIOD_KEY) ?? currentPeriod();
}

function cleanText(raw: string | null | undefined, max = 120): string {
  const t = (raw || "").replace(/\s+/g, " ").trim();
  if (!t) return "";
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

const BLOCK_TAGS = new Set([
  "SECTION",
  "ARTICLE",
  "ASIDE",
  "LI",
  "TR",
  "BUTTON",
  "A",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "P",
  "TD",
  "TH",
  "FIGURE",
  "HEADER",
  "FOOTER",
  "NAV",
  "FORM",
  "TABLE",
  "UL",
  "OL",
  "DL",
  "DIV",
  "SPAN",
  "LABEL",
  "BLOCKQUOTE",
  "PRE",
]);

function isChromeUi(el: Element): boolean {
  return Boolean(
    el.closest(
      "[data-copilot-panel], [data-copilot-chrome], [data-slot=sidebar], [data-slot=sidebar-wrapper], [data-slot=sheet-content], [role=dialog], [data-sonner-toaster]",
    ),
  );
}

function isCompactBlock(el: HTMLElement, main: Element): boolean {
  const h = el.offsetHeight;
  const w = el.offsetWidth;
  if (h < 16 || w < 16) return false;
  // Avoid highlighting the whole scroll viewport.
  if (h > main.clientHeight * 0.85 || w > main.clientWidth * 0.98) return false;
  return true;
}

function hasSelectableContent(el: Element): boolean {
  return cleanText(el.textContent, 400).length >= 3;
}

/** Skip empty layout shells that only wrap a single child filling them. */
function isLayoutOnlyDiv(el: HTMLElement): boolean {
  if (el.tagName !== "DIV") return false;
  if (el.dataset.surfaceId || el.dataset.slot || el.dataset.selectable) return false;
  const kids = Array.from(el.children).filter((c) => c instanceof HTMLElement);
  if (kids.length !== 1) return false;
  const child = kids[0];
  const own = cleanText(
    Array.from(el.childNodes)
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => n.textContent || "")
      .join(" "),
    80,
  );
  if (own.length >= 8) return false;
  const er = el.getBoundingClientRect();
  const cr = child.getBoundingClientRect();
  if (er.width < 1 || er.height < 1) return true;
  const cover =
    (cr.width * cr.height) / Math.max(er.width * er.height, 1);
  return cover > 0.92;
}

function isContentBlock(el: HTMLElement, main: Element): boolean {
  if (!isCompactBlock(el, main) || !hasSelectableContent(el)) return false;
  if (el.tagName === "DIV") {
    if (isLayoutOnlyDiv(el)) return false;
    return true;
  }
  if (el.tagName === "SPAN" || el.tagName === "LABEL") {
    // Require a bit more text so we don't latch onto tiny chrome labels.
    return cleanText(el.textContent, 400).length >= 8;
  }
  return BLOCK_TAGS.has(el.tagName);
}

/** Snap grid/gap clicks to the nearest instrumented tile when the pointer misses it. */
function nearestSurfaceAt(
  root: Element,
  x: number,
  y: number,
  maxDist = 96,
): Element | null {
  const surfaces = root.querySelectorAll("[data-surface-id]");
  let best: Element | null = null;
  let bestDist = Infinity;
  for (const el of surfaces) {
    if (!(el instanceof HTMLElement) || isChromeUi(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const dx = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
    const dy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
    const d = Math.hypot(dx, dy);
    if (d < bestDist) {
      bestDist = d;
      best = el;
    }
  }
  return best && bestDist <= maxDist ? best : null;
}

/**
 * Prefer the innermost meaningful content block (p, section, div, text span, …).
 * Fall back to nearest surface / parent card when the pointer is on padding or grid gaps.
 */
function resolveTarget(
  from: Element | null,
  point?: { x: number; y: number },
): Element | null {
  if (!from || isChromeUi(from)) return null;
  const main = from.closest("[data-copilot-main]");
  if (!main || !main.contains(from)) return null;

  const surface = from.closest("[data-surface-id]");
  const card = from.closest("[data-slot=card]");
  const stopAt = surface || card || main;

  let cur: Element | null = from;
  while (cur && cur !== stopAt && main.contains(cur)) {
    if (cur instanceof HTMLElement) {
      const slot = cur.dataset.slot;
      if (slot === "table-row" || slot === "alert") return cur;
      if (
        (cur.getAttribute("role") === "button" ||
          cur.getAttribute("role") === "link") &&
        isCompactBlock(cur, main) &&
        hasSelectableContent(cur)
      ) {
        return cur;
      }
      if (isContentBlock(cur, main)) return cur;
    }
    cur = cur.parentElement;
  }

  // Pointer may land on the content block that *is* the surface/card root.
  if (
    stopAt instanceof HTMLElement &&
    stopAt !== main &&
    isContentBlock(stopAt, main)
  ) {
    return stopAt;
  }

  // Grid gaps / padding: snap to the closest tile under the same card or container.
  if (point) {
    const snapRoot = card || from;
    const near = nearestSurfaceAt(snapRoot, point.x, point.y);
    if (near && main.contains(near)) return near;
  }

  if (surface && main.contains(surface)) return surface;
  // Allow full-width cards as a fallback so empty padding still attaches context.
  if (card && main.contains(card)) return card;

  cur = from;
  while (cur && cur !== main) {
    if (cur instanceof HTMLElement && isContentBlock(cur, main)) return cur;
    cur = cur.parentElement;
  }

  if (from instanceof HTMLElement && from !== main && isContentBlock(from, main)) {
    return from;
  }
  return null;
}

function labelFor(el: Element): string {
  if (el instanceof HTMLElement) {
    const aria = cleanText(el.getAttribute("aria-label"));
    if (aria) return aria;
    const title = cleanText(el.getAttribute("title"));
    if (title) return title;
  }
  const heading = el.querySelector("h1, h2, h3, h4, h5, h6, [data-slot=card-title]");
  const fromHeading = cleanText(heading?.textContent, 80);
  if (fromHeading) return fromHeading;

  const fromSelf = cleanText(el.textContent, 80);
  if (fromSelf) return fromSelf;

  return el.tagName.toLowerCase();
}

function synthesizeSelection(
  el: Element,
  route: string,
  period: string,
): UiSelection {
  const label = labelFor(el);
  const tag = el.tagName.toLowerCase();
  const slot =
    el instanceof HTMLElement ? el.dataset.slot || el.dataset.surfaceType : undefined;
  const idSeed = cleanText(
    [
      slot || tag,
      label.slice(0, 40),
      el instanceof HTMLElement ? el.id : "",
    ]
      .filter(Boolean)
      .join("."),
    64,
  );
  const text = cleanText(el.textContent, 600);
  return {
    type: "page_region",
    id: `region.${idSeed || tag}`,
    label,
    route,
    period,
    dataSnapshot: {
      tag,
      slot: slot || null,
      text,
      path: route,
    },
  };
}

function selectionFor(el: Element, route: string, period: string): UiSelection | null {
  const surfaceId =
    el instanceof HTMLElement
      ? el.dataset.surfaceId
      : el.getAttribute("data-surface-id");
  if (surfaceId) {
    const registered = surfaceRegistry.get(surfaceId);
    if (registered) return registered;
  }
  return synthesizeSelection(el, route, period);
}

type HoverState = {
  rect: DOMRect;
  label: string;
};

/** Page-wide select mode: hover + click any region in main content, not only cards. */
function SelectModeLayer() {
  const { selectMode } = useCopilotPanel();
  const { pick } = useUiSelection();
  const pathname = usePathname();
  const [hover, setHover] = useState<HoverState | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!selectMode) {
      setHover(null);
      return;
    }

    const main = () => document.querySelector("[data-copilot-main]");

    const onMove = (e: MouseEvent) => {
      const t = e.target;
      if (!(t instanceof Element)) {
        setHover(null);
        return;
      }
      const resolved = resolveTarget(t, { x: e.clientX, y: e.clientY });
      if (!resolved) {
        setHover(null);
        return;
      }
      const rect = resolved.getBoundingClientRect();
      if (rect.width < 4 || rect.height < 4) {
        setHover(null);
        return;
      }
      const period = readPeriod();
      const route = `${pathname}${typeof window !== "undefined" ? window.location.search : ""}`;
      const sel = selectionFor(resolved, route, period);
      setHover({
        rect,
        label: sel?.label || labelFor(resolved),
      });
    };

    const onClick = (e: MouseEvent) => {
      const t = e.target;
      if (!(t instanceof Element)) return;
      if (isChromeUi(t)) return;
      if (!t.closest("[data-copilot-main]")) return;
      const resolved = resolveTarget(t, { x: e.clientX, y: e.clientY });
      if (!resolved) return;
      e.preventDefault();
      e.stopPropagation();
      const period = readPeriod();
      const route = `${pathname}${window.location.search}`;
      const sel = selectionFor(resolved, route, period);
      if (sel) pick(sel);
    };

    const onScroll = () => setHover(null);

    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("click", onClick, true);
    main()?.addEventListener("scroll", onScroll, true);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousemove", onMove, true);
      document.removeEventListener("click", onClick, true);
      main()?.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [selectMode, pick, pathname]);

  useEffect(() => {
    if (!selectMode) return;
    const prev = document.body.style.cursor;
    document.body.style.cursor = "crosshair";
    return () => {
      document.body.style.cursor = prev;
    };
  }, [selectMode]);

  if (!mounted || !selectMode || !hover) return null;

  const { rect, label } = hover;
  return createPortal(
    <div
      aria-hidden
      className="pointer-events-none fixed z-[200] rounded-xl outline outline-2 outline-primary/70 transition-[top,left,width,height] duration-75"
      style={{
        top: rect.top - 2,
        left: rect.left - 2,
        width: rect.width + 4,
        height: rect.height + 4,
      }}
    >
      <span className="absolute -top-2 right-2 translate-y-[-100%] rounded-md bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground shadow-sm">
        Ask · {label}
      </span>
    </div>,
    document.body,
  );
}

export function SelectableSurface({
  selection,
  children,
  className,
  style,
  as: Tag = "div",
}: {
  selection: UiSelection;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  as?: "div" | "span" | "tr" | "li" | "section";
}) {
  const { pick, selection: current } = useUiSelection();
  const { selectMode } = useCopilotPanel();
  const active = current?.id === selection.id;

  useEffect(() => {
    surfaceRegistry.set(selection.id, selection);
    return () => {
      surfaceRegistry.delete(selection.id);
    };
  }, [selection]);

  const onPick = (e: ReactMouseEvent) => {
    if (!selectMode) return;
    const t = e.target;
    // Defer to a tighter paragraph / section / text block inside this surface.
    if (t instanceof Element) {
      const resolved = resolveTarget(t, { x: e.clientX, y: e.clientY });
      if (resolved && resolved !== e.currentTarget) return;
    }
    e.preventDefault();
    e.stopPropagation();
    pick(selection);
  };

  return (
    <Tag
      data-slot={Tag === "tr" ? "table-row" : undefined}
      data-surface-type={selection.type}
      data-surface-id={selection.id}
      data-selectable={selectMode ? "true" : undefined}
      data-selected={active ? "true" : undefined}
      className={cn(
        Tag === "tr" &&
          "border-b border-border/70 transition-colors hover:bg-muted/40",
        className,
        selectMode && "relative cursor-crosshair",
        selectMode && active && "outline outline-2 outline-offset-2 outline-primary",
      )}
      style={style}
      onClickCapture={selectMode ? onPick : undefined}
      onKeyDown={
        selectMode && Tag !== "tr"
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                pick(selection);
              }
            }
          : undefined
      }
      role={selectMode && Tag !== "tr" ? "button" : undefined}
      tabIndex={selectMode && Tag !== "tr" ? 0 : undefined}
      title={selectMode ? `Ask Copilot about ${selection.label}` : undefined}
    >
      {children}
    </Tag>
  );
}
