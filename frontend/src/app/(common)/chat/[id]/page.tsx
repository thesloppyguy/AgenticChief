"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  agentLabelFor,
  ChatMessages,
} from "@/components/chat/chat-messages";
import { PromptComposer } from "@/components/chat/prompt-composer";
import { useChatSession } from "@/components/chat/chat-session-context";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { SessionDetail } from "@/lib/types";

export default function ChatSessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idParam } = use(params);
  const id = Number(idParam);
  const {
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
    openSession,
  } = useChatSession();

  const detail = useApi<SessionDetail>(
    Number.isFinite(id) ? `/copilot/sessions/${id}` : null,
  );

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    void openSession(id);
  }, [id, openSession]);

  const loading = messages.length === 0 && !busy && detail.loading;
  const missing =
    messages.length === 0 && !busy && !detail.loading && !!detail.error;

  return (
    <div className="flex h-[calc(100svh-5.5rem)] min-h-0 flex-col gap-4">
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-card shadow-sm ring-1 ring-black/5 dark:ring-white/10">
        {missing ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6">
            <Loading error={detail.error} loading={false} />
            <Button variant="outline" size="sm" render={<Link href="/chat" />}>
              New chat
            </Button>
          </div>
        ) : loading ? (
          <div className="flex flex-1 items-center justify-center p-6">
            <Loading error={null} loading />
          </div>
        ) : (
          <>
            <ChatMessages
              messages={messages}
              agentLabel={agentLabelFor(agent, modes)}
            />
            <div className="border-t p-3">
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
          </>
        )}
      </div>

      {detail.data?.approvals && detail.data.approvals.length > 0 && (
        <Card title="Proposed from this session">
          <ul className="space-y-1 text-sm">
            {detail.data.approvals.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <Link href={`/actions?id=${a.id}`} className="hover:underline">
                  {a.summary}
                </Link>
                <Badge variant="outline">{label(a.status)}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
