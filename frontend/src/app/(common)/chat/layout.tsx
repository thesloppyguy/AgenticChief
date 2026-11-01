"use client";

import { ChatSessionProvider } from "@/components/chat/chat-session-context";

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <ChatSessionProvider>{children}</ChatSessionProvider>;
}
