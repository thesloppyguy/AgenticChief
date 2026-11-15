"use client";

import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useCopilotPanel } from "./copilot-panel-context";
import { useUiSelection, type UiSelection } from "./ui-selection";

/** Opens the right-rail Copilot, optionally attaching a UI selection. */
export function AskCopilotButton({
  selection,
  children = "Ask the Co-Pilot",
  ...props
}: Omit<ComponentProps<typeof Button>, "onClick"> & {
  selection?: UiSelection;
  children?: ReactNode;
}) {
  const { setOpen } = useCopilotPanel();
  const { pick, clearSelection } = useUiSelection();

  return (
    <Button
      type="button"
      {...props}
      onClick={() => {
        if (selection) pick(selection);
        else {
          clearSelection();
          setOpen(true);
        }
      }}
    >
      {children}
    </Button>
  );
}
