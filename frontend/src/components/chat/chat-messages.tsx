"use client";

import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  Message,
  MessageContent,
  MessageGroup,
  MessageHeader,
} from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { ChatArtifacts } from "./chat-artifacts";
import { ToolTrace } from "./tool-trace";
import type { AgentOption, ChatMsg } from "./types";

export function ChatMessages({
  messages,
  agentLabel,
}: {
  messages: ChatMsg[];
  agentLabel: string;
}) {
  return (
    <MessageScrollerProvider>
      <MessageScroller className="min-h-0 flex-1">
        <MessageScrollerViewport className="p-4">
          <MessageScrollerContent>
            <MessageGroup>
              {messages.map((m, i) => (
                <MessageScrollerItem
                  key={i}
                  scrollAnchor={i === messages.length - 1}
                >
                  <Message align={m.role === "user" ? "end" : "start"}>
                    <MessageContent>
                      {m.role === "assistant" && (
                        <>
                          <MessageHeader>{agentLabel}</MessageHeader>
                          <ToolTrace tools={m.tools} live={!m.done} />
                        </>
                      )}
                      <Bubble
                        variant={m.role === "user" ? "default" : "muted"}
                        align={m.role === "user" ? "end" : "start"}
                      >
                        <BubbleContent className="whitespace-pre-wrap">
                          {m.content || (m.done ? "" : "Thinking…")}
                          {m.attachments && m.attachments.length > 0 && (
                            <span className="mt-2 block text-xs opacity-80">
                              Attached: {m.attachments.join(", ")}
                            </span>
                          )}
                          {m.role === "assistant" && (
                            <ChatArtifacts artifacts={m.artifacts} />
                          )}
                        </BubbleContent>
                      </Bubble>
                    </MessageContent>
                  </Message>
                </MessageScrollerItem>
              ))}
            </MessageGroup>
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton direction="end" />
      </MessageScroller>
    </MessageScrollerProvider>
  );
}

export function agentLabelFor(
  agent: string,
  modes: AgentOption[],
): string {
  return modes.find((o) => o.value === agent)?.label ?? "Copilot";
}
