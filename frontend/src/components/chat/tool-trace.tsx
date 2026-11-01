"use client";

import { Terminal, Users } from "lucide-react";
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace";
import { label } from "@/lib/format";

/** Specialist consults read differently from ordinary tools. */
export function ToolTrace({ tools, live }: { tools: string[]; live: boolean }) {
  if (tools.length === 0) return null;
  return (
    <Trace className="mb-2">
      {[...new Set(tools)].map((t) => {
        const delegated = t === "consult_specialist" || t === "delegate";
        return (
          <TraceLine key={t} status={live ? "running" : undefined}>
            <TraceIcon>
              {delegated ? (
                <Users className="size-3.5" />
              ) : (
                <Terminal className="size-3.5" />
              )}
            </TraceIcon>
            <TraceTitle>
              {delegated
                ? "Asked a specialist"
                : `Used ${label(t.replace(/^cap_/, ""))}`}
            </TraceTitle>
          </TraceLine>
        );
      })}
    </Trace>
  );
}
