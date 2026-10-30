"use client";
import { use } from "react";
import Link from "next/link";
import { Terminal } from "lucide-react";
import { Card, Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  Message, MessageContent, MessageGroup, MessageHeader,
} from "@/components/ui/message";
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace";
import { label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { SessionDetail } from "@/lib/types";

export default function ChatSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading } = useApi<SessionDetail>(`/copilot/sessions/${id}`);

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{data?.title ?? "Session"}</h1>
          <p className="text-sm text-muted-foreground">A past conversation, exactly as it ran.</p>
        </div>
        <Button variant="outline" size="sm" render={<Link href="/chat" />}>New question</Button>
      </div>

      <Loading error={error} loading={loading && !data} />

      {data && (
        <MessageGroup>
          {data.messages.map((m, i) => (
            <Message key={i} align={m.role === "user" ? "end" : "start"}>
              <MessageContent>
                {m.role === "assistant" && (
                  <>
                    <MessageHeader>Copilot</MessageHeader>
                    {m.tools && m.tools.length > 0 && (
                      <Trace className="mb-2">
                        {[...new Set(m.tools)].map((t) => (
                          <TraceLine key={t}>
                            <TraceIcon><Terminal className="size-3.5" /></TraceIcon>
                            <TraceTitle>Used {label(t)}</TraceTitle>
                          </TraceLine>
                        ))}
                      </Trace>
                    )}
                  </>
                )}
                <Bubble variant={m.role === "user" ? "default" : "muted"}
                  align={m.role === "user" ? "end" : "start"}>
                  <BubbleContent className="whitespace-pre-wrap">{m.content}</BubbleContent>
                </Bubble>
              </MessageContent>
            </Message>
          ))}
        </MessageGroup>
      )}

      {data?.approvals && data.approvals.length > 0 && (
        <Card title="Proposed from this session">
          <ul className="space-y-1 text-sm">
            {data.approvals.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <Link href={`/actions?id=${a.id}`} className="hover:underline">{a.summary}</Link>
                <Badge variant="outline">{label(a.status)}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
