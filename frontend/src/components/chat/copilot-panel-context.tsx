"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

const OPEN_KEY = "chro_copilot_open";
const WIDTH_KEY = "chro_copilot_width";
const OPEN_EVENT = "chro:copilot-open";
const WIDTH_EVENT = "chro:copilot-width";
const SELECT_EVENT = "chro:copilot-select-mode";

const DEFAULT_WIDTH = 400;
const MIN_WIDTH = 320;
const MAX_WIDTH = 640;

function clampWidth(n: number) {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(n)));
}

function subscribeOpen(onChange: () => void) {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === OPEN_KEY || e.key === null) onChange();
  };
  window.addEventListener(OPEN_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(OPEN_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function subscribeWidth(onChange: () => void) {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === WIDTH_KEY || e.key === null) onChange();
  };
  window.addEventListener(WIDTH_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(WIDTH_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

let selectMode = false;
const selectListeners = new Set<() => void>();

function subscribeSelect(onChange: () => void) {
  selectListeners.add(onChange);
  return () => {
    selectListeners.delete(onChange);
  };
}

function emitSelect() {
  selectListeners.forEach((l) => l());
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SELECT_EVENT));
  }
}

type CopilotPanelContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  width: number;
  setWidth: (width: number) => void;
  selectMode: boolean;
  setSelectMode: (on: boolean) => void;
  openAndSelect: () => void;
};

const CopilotPanelContext = createContext<CopilotPanelContextValue | null>(null);

export function CopilotPanelProvider({ children }: { children: ReactNode }) {
  const open = useSyncExternalStore(
    subscribeOpen,
    () => localStorage.getItem(OPEN_KEY) === "1",
    () => false,
  );
  const width = useSyncExternalStore(
    subscribeWidth,
    () => {
      const raw = localStorage.getItem(WIDTH_KEY);
      const n = raw ? Number(raw) : DEFAULT_WIDTH;
      return Number.isFinite(n) ? clampWidth(n) : DEFAULT_WIDTH;
    },
    () => DEFAULT_WIDTH,
  );
  const selectOn = useSyncExternalStore(
    subscribeSelect,
    () => selectMode,
    () => false,
  );

  const setOpen = useCallback((next: boolean) => {
    localStorage.setItem(OPEN_KEY, next ? "1" : "0");
    window.dispatchEvent(new Event(OPEN_EVENT));
    if (!next) {
      selectMode = false;
      emitSelect();
    }
  }, []);

  const toggle = useCallback(() => {
    setOpen(!(localStorage.getItem(OPEN_KEY) === "1"));
  }, [setOpen]);

  const setWidth = useCallback((next: number) => {
    localStorage.setItem(WIDTH_KEY, String(clampWidth(next)));
    window.dispatchEvent(new Event(WIDTH_EVENT));
  }, []);

  const setSelectMode = useCallback((on: boolean) => {
    selectMode = on;
    emitSelect();
  }, []);

  const openAndSelect = useCallback(() => {
    localStorage.setItem(OPEN_KEY, "1");
    window.dispatchEvent(new Event(OPEN_EVENT));
    selectMode = true;
    emitSelect();
  }, []);

  // Cmd/Ctrl+L — open panel and enter select mode (Cursor-like).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "l") return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      openAndSelect();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openAndSelect]);

  // Escape exits select mode.
  useEffect(() => {
    if (!selectOn) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        selectMode = false;
        emitSelect();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectOn]);

  const value = useMemo(
    () => ({
      open,
      setOpen,
      toggle,
      width,
      setWidth,
      selectMode: selectOn,
      setSelectMode,
      openAndSelect,
    }),
    [open, setOpen, toggle, width, setWidth, selectOn, setSelectMode, openAndSelect],
  );

  return (
    <CopilotPanelContext.Provider value={value}>
      {children}
    </CopilotPanelContext.Provider>
  );
}

export function useCopilotPanel() {
  const ctx = useContext(CopilotPanelContext);
  if (!ctx) {
    throw new Error("useCopilotPanel must be used within CopilotPanelProvider");
  }
  return ctx;
}

export { DEFAULT_WIDTH, MIN_WIDTH, MAX_WIDTH, clampWidth };
