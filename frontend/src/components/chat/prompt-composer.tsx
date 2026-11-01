"use client";

import { useRef } from "react";
import { ArrowUp, FileText, Paperclip, X } from "lucide-react";
import {
  Attachment,
  AttachmentAction,
  AttachmentActions,
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
} from "@/components/ui/attachment";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentOption } from "./types";

const ACCEPT =
  ".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.png,.jpg,.jpeg,.webp";

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function PromptComposer({
  text,
  onTextChange,
  files,
  onFilesChange,
  agent,
  onAgentChange,
  modes,
  busy,
  onSend,
  placeholder = "Ask anything about the group…",
}: {
  text: string;
  onTextChange: (v: string) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  agent: string;
  onAgentChange: (v: string) => void;
  modes: AgentOption[];
  busy: boolean;
  onSend: (prompt?: string) => void;
  placeholder?: string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);

  function addFiles(list: FileList | null) {
    if (!list?.length) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue;
      if (next.length >= 5) break;
      next.push(f);
    }
    onFilesChange(next);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div className="space-y-2">
      {files.length > 0 && (
        <AttachmentGroup>
          {files.map((f) => (
            <Attachment key={`${f.name}-${f.size}`} size="sm">
              <AttachmentMedia>
                <FileText />
              </AttachmentMedia>
              <AttachmentContent>
                <AttachmentTitle>{f.name}</AttachmentTitle>
                <AttachmentDescription>
                  {formatBytes(f.size)}
                </AttachmentDescription>
              </AttachmentContent>
              <AttachmentActions>
                <AttachmentAction
                  aria-label={`Remove ${f.name}`}
                  onClick={() =>
                    onFilesChange(
                      files.filter(
                        (x) => !(x.name === f.name && x.size === f.size),
                      ),
                    )
                  }
                >
                  <X />
                </AttachmentAction>
              </AttachmentActions>
            </Attachment>
          ))}
        </AttachmentGroup>
      )}

      <InputGroup className="rounded-[1.35rem] border-transparent bg-muted/80 shadow-md ring-1 ring-black/[0.04]">
        <InputGroupTextarea
          rows={2}
          value={text}
          placeholder={placeholder}
          onChange={(e) => onTextChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
        />
        <InputGroupAddon align="block-end" className="justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            <input
              ref={fileRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => addFiles(e.target.files)}
            />
            <InputGroupButton
              size="icon-sm"
              className="rounded-full"
              disabled={busy || files.length >= 5}
              onClick={() => fileRef.current?.click()}
              aria-label="Attach files"
            >
              <Paperclip className="size-4" />
            </InputGroupButton>
            <Select
              items={modes}
              value={agent}
              onValueChange={(v) => {
                if (v != null) onAgentChange(v);
              }}
            >
              <SelectTrigger
                size="sm"
                aria-label="Mode"
                className="h-8 min-w-40 max-w-56 gap-2 border-transparent bg-transparent px-2.5 shadow-none"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent
                align="start"
                alignItemWithTrigger={false}
                className="min-w-56 p-1.5"
              >
                {modes.map((m) => (
                  <SelectItem
                    key={m.value || "default"}
                    value={m.value}
                    className="rounded-lg py-2 pr-10 pl-2.5"
                  >
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <InputGroupButton
            variant="default"
            size="icon-sm"
            className="rounded-full bg-primary text-primary-foreground shadow-sm hover:bg-[color-mix(in_srgb,var(--primary),#000_8%)]"
            disabled={busy || (!text.trim() && files.length === 0)}
            onClick={() => onSend()}
            aria-label="Send"
          >
            <ArrowUp className="size-4" />
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </div>
  );
}
