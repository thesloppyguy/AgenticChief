import { API_URL, getToken } from "./api";

/** Read a Server-Sent Events stream with the auth header (EventSource cannot send one). Resolves when it ends. */
export async function readSse(path: string, onEvent: (name: string, data: unknown) => void, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${getToken()}`, Accept: "text/event-stream" },
      signal,
    });
  } catch {
    // Network down, CORS, or abort — caller decides whether to reconnect.
    if (signal.aborted) return;
    throw new Error("stream unreachable");
  }
  if (!res.ok || !res.body) throw new Error(`stream refused (${res.status})`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buf += dec.decode(value, { stream: true });
      const frames = buf.split(/\r?\n\r?\n/);
      buf = frames.pop() ?? "";
      for (const frame of frames) {
        let name = "message";
        const data: string[] = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) name = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).trim());
        }  // lines starting with ":" are keep-alive comments
        if (data.length) { try { onEvent(name, JSON.parse(data.join("\n"))); } catch { /* ignore a malformed frame */ } }
      }
    }
  } catch {
    if (signal.aborted) return;
    throw new Error("stream interrupted");
  }
}
