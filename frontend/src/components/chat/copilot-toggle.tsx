"use client";

import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCopilotPanel } from "./copilot-panel-context";

export function CopilotToggle() {
  const { open, toggle } = useCopilotPanel();

  return (
    <Button
      type="button"
      variant={open ? "default" : "ghost"}
      size="icon-sm"
      aria-label={open ? "Close Copilot" : "Open Copilot"}
      aria-pressed={open}
      title="Copilot (⌘L to select)"
      onClick={toggle}
    >
      <Bot className="size-4" />
    </Button>
  );
}
