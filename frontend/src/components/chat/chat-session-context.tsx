"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { usePeriod } from "@/components/AppShell";
import { API_URL, getToken } from "@/lib/api";
import { streamChat } from "@/lib/chat";
import { useApi } from "@/lib/hooks";
import { SESSIONS_CHANGED, type SessionDetail } from "@/lib/types";
import type { AgentOption, ChatArtifact, ChatMsg } from "./types";

const DEFAULT_MODE = "__default__";

type ChatSessionContextValue = {
  sessionId: number | null;
  messages: ChatMsg[];
  text: string;
  setText: (v: string) => void;
  files: File[];
  setFiles: (files: File[]) => void;
  agent: string;
  setAgent: (v: string) => void;
  modes: AgentOption[];
  busy: boolean;
  send: (prompt?: string) => Promise<void>;
  resetNew: (agentHint?: string) => void;
  openSession: (id: number) => Promise<void>;
};

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

async function uploadAttachments(files: File[]): Promise<string[]> {
  const titles: string[] = [];
  for (const file of files) {
    const body = new FormData();
    body.append("file", file);
    body.append("title", file.name);
    body.append("domain", "general");
    try {
      const res = await fetch(`${API_URL}/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body,
      });
      if (res.ok) {
        const doc = (await res.json()) as { title?: string };
        titles.push(doc.title || file.name);
      } else {
        titles.push(file.name);
      }
    } catch {
      titles.push(file.name);
    }
  }
  return titles;
}

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [period] = usePeriod();
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [agent, setAgent] = useState(DEFAULT_MODE);
  const [busy, setBusy] = useState(false);
  const genRef = useRef(0);
  const loadedRef = useRef<number | null>(null);
  const liveRef = useRef({ busy: false, sessionId: null as number | null, messages: [] as ChatMsg[] });
  liveRef.current = { busy, sessionId, messages };

  const agents = useApi<{ name: string; role: string }[]>("/agents");

  const modes = useMemo<AgentOption[]>(
    () => [
      { value: DEFAULT_MODE, label: "Executive (default)" },
      ...(agents.data ?? [])
        .filter((a) => a.name !== "executive")
        .map((a) => ({ value: a.name, label: a.role })),
    ],
    [agents.data],
  );

  const patchLast = useCallback((fn: (m: ChatMsg) => ChatMsg) => {
    setMessages((all) =>
      all.map((m, i) => (i === all.length - 1 ? fn(m) : m)),
    );
  }, []);

  const resetNew = useCallback((agentHint?: string) => {
    genRef.current += 1;
    loadedRef.current = null;
    setSessionId(null);
    setMessages([]);
    setText("");
    setFiles([]);
    setBusy(false);
    if (agentHint !== undefined) {
      setAgent(agentHint || DEFAULT_MODE);
    }
  }, []);

  const openSession = useCallback(async (id: number) => {
    const live = liveRef.current;
    // Keep an in-flight turn (including the first prompt handoff from /chat).
    if (
      live.busy ||
      live.messages.some((m) => m.role === "assistant" && !m.done)
    ) {
      loadedRef.current = id;
      setSessionId(id);
      return;
    }
    if (loadedRef.current === id && live.sessionId === id && live.messages.length > 0) {
      return;
    }
    const gen = ++genRef.current;
    try {
      const detail = await fetch(`${API_URL}/copilot/sessions/${id}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      }).then(async (res) => {
        if (!res.ok) throw new Error("Session not found");
        return res.json() as Promise<SessionDetail>;
      });
      if (gen !== genRef.current) return;
      loadedRef.current = id;
      setSessionId(id);
      setMessages(
        detail.messages.map((m) => ({
          role: (m.role === "user" ? "user" : "assistant") as ChatMsg["role"],
          content: m.content,
          tools: m.tools ?? [],
          artifacts: (m.artifacts as ChatArtifact[] | null | undefined) ?? undefined,
          done: true,
        })),
      );
      setBusy(false);
    } catch {
      if (gen !== genRef.current) return;
      setMessages([
        {
          role: "assistant",
          content: "Could not load this conversation.",
          tools: [],
          done: true,
        },
      ]);
    }
  }, []);

  const send = useCallback(
    async (prompt?: string) => {
      const body = (prompt ?? text).trim();
      if ((!body && files.length === 0) || busy) return;

      const gen = genRef.current;
      const pendingFiles = files;
      const attachmentNames = pendingFiles.map((f) => f.name);
      const currentSession = sessionId;
      setText("");
      setFiles([]);
      setBusy(true);
      setMessages((all) => [
        ...all,
        {
          role: "user",
          content: body || "See attached files.",
          tools: [],
          done: true,
          attachments: attachmentNames.length ? attachmentNames : undefined,
        },
        { role: "assistant", content: "", tools: [], artifacts: [], done: false },
      ]);

      let apiMessage = body || "Please review the attached documents.";
      if (pendingFiles.length > 0) {
        const uploaded = await uploadAttachments(pendingFiles);
        if (gen !== genRef.current) return;
        apiMessage = `${apiMessage}\n\n[Attached documents available via search: ${uploaded.join(", ")}]`;
      }

      const agentKey = agent === DEFAULT_MODE ? undefined : agent;
      let routed = false;

      await streamChat(
        {
          message: apiMessage,
          session_id: currentSession,
          period,
          ...(agentKey ? { agent_key: agentKey } : {}),
        },
        {
          onSession: (id) => {
            if (gen !== genRef.current) return;
            setSessionId(id);
            loadedRef.current = id;
            if (!routed && currentSession == null) {
              routed = true;
              router.replace(`/chat/${id}`);
              window.dispatchEvent(new Event(SESSIONS_CHANGED));
            }
          },
          onChunk: (c) => {
            if (gen !== genRef.current) return;
            patchLast((m) => ({ ...m, content: m.content + c }));
          },
          onTool: (n) => {
            if (gen !== genRef.current) return;
            patchLast((m) => ({ ...m, tools: [...m.tools, n] }));
          },
          onArtifact: (art) => {
            if (gen !== genRef.current) return;
            patchLast((m) => ({
              ...m,
              artifacts: [...(m.artifacts ?? []), art as ChatArtifact],
            }));
          },
          onError: (e) => {
            if (gen !== genRef.current) return;
            patchLast((m) => ({ ...m, content: e, done: true }));
          },
          onDone: (id) => {
            if (gen !== genRef.current) return;
            setSessionId(id);
            loadedRef.current = id;
            patchLast((m) => ({ ...m, done: true }));
            window.dispatchEvent(new Event(SESSIONS_CHANGED));
            if (!routed && currentSession == null) {
              routed = true;
              router.replace(`/chat/${id}`);
            }
          },
        },
      );

      if (gen === genRef.current) setBusy(false);
    },
    [agent, busy, files, patchLast, period, router, sessionId, text],
  );

  const value = useMemo(
    () => ({
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
      openSession,
    }),
    [
      sessionId,
      messages,
      text,
      files,
      agent,
      modes,
      busy,
      send,
      resetNew,
      openSession,
    ],
  );

  return (
    <ChatSessionContext.Provider value={value}>
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSession() {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error("useChatSession must be used within ChatSessionProvider");
  }
  return ctx;
}

export { DEFAULT_MODE };
