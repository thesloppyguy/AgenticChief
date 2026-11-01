import { API_URL, getToken } from "./api";

export interface ChatBody {
  message?: string; session_id?: number | null; period?: string;
  skill_name?: string; skill_key?: string; skill_inputs?: Record<string, unknown>;
  agent_key?: string; allow_draft?: boolean;
}
export interface ChatHandlers {
  onChunk: (text: string) => void;
  onTool: (name: string) => void;
  onDone: (sessionId: number) => void;
  onError: (message: string) => void;
  /** Fired as soon as the server assigns a session id (before tokens stream). */
  onSession?: (sessionId: number) => void;
  onArtifact?: (artifact: Record<string, unknown>) => void;
}

/** POST /copilot/chat and read its Server-Sent Events. Resolves when the stream ends. */
export async function streamChat(body: ChatBody, h: ChatHandlers): Promise<void> {
  try {
    const res = await fetch(`${API_URL}/copilot/chat`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      let detail = "Request failed";
      if (res.status === 503) detail = "Copilot is not configured on the server.";
      else { try { const j = await res.json(); if (typeof j.detail === "string") detail = j.detail; } catch {} }
      return h.onError(detail);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let sessionSeen = false;
    const noteSession = (id: unknown) => {
      if (sessionSeen || typeof id !== "number") return;
      sessionSeen = true;
      h.onSession?.(id);
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/);
      buf = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.split(/\r?\n/).find((l) => l.startsWith("data:"));
        if (!line) continue;
        const ev = JSON.parse(line.slice(5));
        if (typeof ev.session_id === "number") noteSession(ev.session_id);
        if (ev.type === "session") noteSession(ev.session_id);
        else if (ev.type === "chunk") h.onChunk(ev.content);
        else if (ev.type === "tool") h.onTool(ev.name);
        else if (ev.type === "artifact" && ev.artifact) h.onArtifact?.(ev.artifact);
        else if (ev.type === "error") h.onError(ev.message);
        else if (ev.type === "done") h.onDone(ev.session_id);
      }
    }
  } catch (err) {
    h.onError(err instanceof Error ? err.message : "Request failed");
  }
}
