"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  Crosshair,
  Maximize2,
  PanelRightClose,
  Plus,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";
import { agentLabelFor, ChatMessages } from "./chat-messages";
import { useChatSession } from "./chat-session-context";
import { MAX_WIDTH, MIN_WIDTH, useCopilotPanel } from "./copilot-panel-context";
import { PromptComposer } from "./prompt-composer";
import { useUiSelection } from "./ui-selection";

function SelectionChip({
  label,
  onClear,
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <div className="flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs ring-1 ring-black/[0.04] dark:ring-white/10">
      <Crosshair className="size-3 shrink-0 text-primary" />
      <span className="max-w-[14rem] truncate font-medium">{label}</span>
      <button
        type="button"
        aria-label="Clear selection"
        className="rounded-full p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
        onClick={onClear}
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

function PanelBody({ compact }: { compact?: boolean }) {
  const pathname = usePathname();
  const {
    sessionId,
    messages,
    text,
    setText,
    files,
    setFiles,
    agent,
    setAgent,
    modes,
    busy,
    send,
    resetNew,
  } = useChatSession();
  const { setOpen, selectMode, setSelectMode } = useCopilotPanel();
  const { selection, clearSelection } = useUiSelection();

  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border/70 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-white shadow-sm">
            <Bot className="size-3.5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-tight">
              Copilot
            </div>
            {sessionId ? (
              <div className="truncate text-[11px] text-muted-foreground">
                Session #{sessionId}
              </div>
            ) : (
              <div className="truncate text-[11px] text-muted-foreground">
                New conversation
              </div>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <Button
            type="button"
            variant={selectMode ? "default" : "ghost"}
            size="icon-sm"
            aria-label="Select UI component"
            title="Select anything on the page (⌘L)"
            onClick={() => setSelectMode(!selectMode)}
          >
            <Crosshair className="size-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="New chat"
            onClick={() => resetNew()}
          >
            <Plus className="size-4" />
          </Button>
          {!compact && (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Open full chat"
              render={
                <Link
                  href={sessionId ? `/chat/${sessionId}` : "/chat"}
                  onClick={() => setOpen(false)}
                />
              }
              nativeButton={false}
            >
              <Maximize2 className="size-4" />
            </Button>
          )}
        </div>
      </div>

      {selectMode && (
        <div className="shrink-0 border-b border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
          Click anything on the page to attach it. Esc to cancel.
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {empty ? (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 overflow-hidden px-6 text-center">
            <p className="text-sm text-muted-foreground">
              Ask about anything on the page — scores, pulse, briefs, or any region.
            </p>
            <p className="text-xs text-muted-foreground">
              Use the crosshair or ⌘L, then click to attach it.
            </p>
          </div>
        ) : (
          <ChatMessages
            messages={messages}
            agentLabel={agentLabelFor(agent, modes)}
          />
        )}
      </div>

      <div className="shrink-0 space-y-2 border-t border-border/70 p-3">
        {selection && (
          <SelectionChip label={selection.label} onClear={clearSelection} />
        )}
        <PromptComposer
          text={text}
          onTextChange={setText}
          files={files}
          onFilesChange={setFiles}
          agent={agent}
          onAgentChange={setAgent}
          modes={modes}
          busy={busy}
          onSend={(p) => void send(p)}
          placeholder={
            selection
              ? `Ask about ${selection.label}…`
              : "Ask anything about the group…"
          }
        />
        {pathname.startsWith("/chat") ? null : (
          <p className="text-center text-[10px] text-muted-foreground">
            Full page:{" "}
            <Link
              href={sessionId ? `/chat/${sessionId}` : "/chat"}
              className="underline-offset-2 hover:underline"
              onClick={() => setOpen(false)}
            >
              /chat
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}

function ResizeHandle({ onDrag }: { onDrag: (clientX: number) => void }) {
  const dragging = useRef(false);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      onDrag(e.clientX);
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [onDrag]);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize Copilot"
      className="group absolute inset-y-0 left-0 z-10 w-1.5 -translate-x-1/2 cursor-col-resize"
      onMouseDown={(e) => {
        e.preventDefault();
        dragging.current = true;
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      }}
    >
      <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover:bg-primary/40 group-active:bg-primary/60" />
    </div>
  );
}

/** Desktop right rail. Hidden on /chat (full-page owns the conversation). */
export function CopilotPanelRail() {
  const pathname = usePathname();
  const isMobile = useIsMobile();
  const { open, width, setWidth } = useCopilotPanel();
  const [liveWidth, setLiveWidth] = useState(width);

  useEffect(() => {
    setLiveWidth(width);
  }, [width]);

  const onDrag = useCallback(
    (clientX: number) => {
      const next = Math.min(
        MAX_WIDTH,
        Math.max(MIN_WIDTH, window.innerWidth - clientX),
      );
      setLiveWidth(next);
      setWidth(next);
    },
    [setWidth],
  );

  if (isMobile || pathname.startsWith("/chat") || !open) return null;

  return (
    <aside
      data-copilot-panel
      className={cn(
        "relative flex h-full min-h-0 shrink-0 flex-col overflow-hidden border-l border-border/70 bg-background",
      )}
      style={{ width: liveWidth }}
    >
      <ResizeHandle onDrag={onDrag} />
      <PanelBody />
    </aside>
  );
}

/** Mobile sheet drawer for the Copilot panel. */
export function CopilotPanelSheet() {
  const pathname = usePathname();
  const isMobile = useIsMobile();
  const { open, setOpen } = useCopilotPanel();

  if (!isMobile || pathname.startsWith("/chat")) return null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent
        data-copilot-panel
        side="right"
        showCloseButton={false}
        className="w-[min(100vw,24rem)] gap-0 p-0 sm:max-w-none"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>Copilot</SheetTitle>
        </SheetHeader>
        <PanelBody compact />
      </SheetContent>
    </Sheet>
  );
}
