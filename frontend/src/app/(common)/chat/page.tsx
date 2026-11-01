"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { Bot } from "lucide-react";
import { PromptComposer } from "@/components/chat/prompt-composer";
import {
  DEFAULT_MODE,
  useChatSession,
} from "@/components/chat/chat-session-context";

const EXAMPLES = [
  {
    title: "Group score",
    body: "What is the Group score this month, and what moved?",
  },
  {
    title: "Workforce pulse",
    body: "Show the workforce pulse and top issues for this week.",
  },
  {
    title: "Skills gap",
    body: "Where is the future-skills demand vs supply gap, and what draft action closes it?",
  },
  {
    title: "Succession",
    body: "Which critical roles have weak or no successors?",
  },
];

function NewChat() {
  const params = useSearchParams();
  const agentHint = params.get("agent");
  const {
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

  // /chat is always a fresh session window.
  useEffect(() => {
    resetNew(agentHint ?? DEFAULT_MODE);
  }, [agentHint, resetNew]);

  return (
    <div className="flex h-[calc(100svh-5.5rem)] min-h-0 flex-col gap-4">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-card shadow-sm ring-1 ring-black/5 dark:ring-white/10">
        <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto p-6">
          <div className="w-full max-w-3xl space-y-6">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Try an example</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex.title}
                    type="button"
                    disabled={busy}
                    onClick={() => void send(ex.body)}
                    className="rounded-2xl bg-muted/50 p-4 text-left shadow-sm ring-1 ring-black/5 transition-colors hover:bg-white dark:ring-white/10"
                  >
                    <div className="font-medium">{ex.title}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {ex.body}
                    </div>
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2 text-center">
              <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-neutral-900 text-white shadow-sm dark:bg-neutral-100 dark:text-neutral-900">
                <Bot className="size-6" />
              </div>
              <p className="text-muted-foreground">Good to see you</p>
              <h2 className="text-2xl font-semibold tracking-tight">
                How can I help today?
              </h2>
              <p className="text-sm text-muted-foreground">
                Ask about scores, companies, pillars, or anything in your
                knowledge base.
              </p>
            </div>
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
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <NewChat />
    </Suspense>
  );
}
