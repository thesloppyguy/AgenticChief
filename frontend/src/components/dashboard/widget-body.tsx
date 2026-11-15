"use client";

import { ArtifactBody } from "@/components/chat/chat-artifacts";
import type { ChatArtifact } from "@/components/chat/types";

/** Shared renderer for chat artifacts pinned onto Home. */
export function WidgetBody({ artifact }: { artifact: ChatArtifact }) {
  return <ArtifactBody artifact={artifact} />;
}
