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
import { Markdown } from "./markdown";
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
              {messages.map((m, i) => {
                const assistant = m.role === "assistant";
                const pending = !m.content && !m.done;
                return (
                  <MessageScrollerItem
                    key={i}
                    scrollAnchor={i === messages.length - 1}
                  >
                    <Message align={assistant ? "start" : "end"}>
                      <MessageContent className={assistant ? "max-w-[min(100%,52rem)]" : undefined}>
                        {assistant && (
                          <>
                            <MessageHeader>{agentLabel}</MessageHeader>
                            <ToolTrace tools={m.tools} live={!m.done} />
                          </>
                        )}
                        {(pending || m.content || (m.attachments && m.attachments.length > 0)) && (
                          <Bubble
                            variant={assistant ? "ghost" : "default"}
                            align={assistant ? "start" : "end"}
                            className={assistant ? "max-w-full" : undefined}
                          >
                            <BubbleContent
                              className={
                                assistant
                                  ? "w-full max-w-full px-0"
                                  : "whitespace-pre-wrap"
                              }
                            >
                              {pending ? (
                                <span className="text-muted-foreground">Thinking…</span>
                              ) : assistant && m.content ? (
                                <Markdown>{m.content}</Markdown>
                              ) : (
                                m.content
                              )}
                              {m.attachments && m.attachments.length > 0 && (
                                <span className="mt-2 block text-xs opacity-80">
                                  Attached: {m.attachments.join(", ")}
                                </span>
                              )}
                            </BubbleContent>
                          </Bubble>
                        )}
                        {assistant && <ChatArtifacts artifacts={m.artifacts} />}
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                );
              })}
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
