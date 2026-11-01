"use client";

import { ChatArtifacts } from "@/components/chat/chat-artifacts";
import { Markdown } from "@/components/chat/markdown";
import type { ChatArtifact } from "@/components/chat/types";
import { Card, ScoreTile, StatusBadge } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { fmt, label } from "@/lib/format";
import type { ReportDoc, Status } from "@/lib/types";

type StepPillar = {
  pillar?: string;
  score?: number | null;
  status?: Status | string | null;
};

type CardStep = {
  period?: string;
  scope?: string;
  score?: number | null;
  status?: Status | string | null;
  pillars?: StepPillar[];
  companies_with_data?: number;
  companies_in_scope?: number;
  group?: {
    score?: number | null;
    status?: Status | string | null;
    pillars?: StepPillar[];
  };
};

type AgentStep = {
  text?: string;
  ran?: string;
  seeded?: boolean;
  error?: string;
  skipped?: boolean;
};

export type WorkflowResultDoc = {
  workflow?: string;
  title?: string;
  period?: string;
  summary?: string;
  steps?: Record<string, unknown>;
  artifacts?: ChatArtifact[];
  skipped?: string[];
  commentary?: { text?: string };
};

function asStatus(v: unknown): Status {
  return v === "green" || v === "amber" || v === "red" ? v : null;
}

export function pickCard(steps: Record<string, unknown> | undefined): CardStep | null {
  if (!steps) return null;
  const raw = (steps.card || steps.scorecard || steps.collect) as CardStep | undefined;
  return raw && typeof raw === "object" ? raw : null;
}

/** Prefer the board-ready summarize step over the longer specialist draft. */
export function pickNarrative(
  steps: Record<string, unknown> | undefined,
  result: WorkflowResultDoc,
): string | null {
  if (!steps) return result.commentary?.text || null;
  for (const key of ["summary", "brief", "commentary", "chro", "priorities"]) {
    const step = steps[key] as AgentStep | string | undefined;
    if (!step) continue;
    if (typeof step === "string" && step.trim()) return step;
    if (typeof step === "object") {
      if (typeof step.text === "string" && step.text.trim()) return step.text;
    }
  }
  return result.commentary?.text || null;
}

function hasScorecardSummary(artifacts: ChatArtifact[]): boolean {
  return artifacts.some((a) => a.kind === "scorecard_summary");
}

function ScorecardStrip({ card }: { card: CardStep }) {
  const score = card.score ?? card.group?.score ?? null;
  const status = asStatus(card.status ?? card.group?.status);
  const pillars = card.pillars ?? card.group?.pillars ?? [];
  if (score == null && pillars.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <ScoreTile
          title="Group score"
          score={typeof score === "number" ? score : null}
          status={status}
          note={
            card.companies_with_data != null
              ? `${card.companies_with_data}/${card.companies_in_scope ?? "—"} companies with data`
              : card.period
                ? `Period ${card.period}`
                : undefined
          }
          accent
        />
        {pillars.slice(0, 3).map((p) => (
          <ScoreTile
            key={String(p.pillar)}
            title={label(String(p.pillar || ""))}
            score={typeof p.score === "number" ? p.score : null}
            status={asStatus(p.status)}
          />
        ))}
      </div>
      {pillars.length > 3 ? (
        <div className="flex flex-wrap gap-2">
          {pillars.slice(3).map((p) => (
            <div
              key={String(p.pillar)}
              className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background px-3 py-1 text-xs"
            >
              <span className="font-medium">{label(String(p.pillar || ""))}</span>
              <span className="tabular-nums text-muted-foreground">
                {fmt(typeof p.score === "number" ? p.score : null, 0)}
              </span>
              <StatusBadge status={asStatus(p.status)} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function WorkflowResultView({
  result,
}: {
  result: WorkflowResultDoc;
}) {
  const card = pickCard(result.steps);
  const narrative = pickNarrative(result.steps, result);
  const artifacts = result.artifacts || [];
  const skipped = result.skipped || [];
  const glance = result.summary?.trim() || null;
  const showStrip = !!card && !hasScorecardSummary(artifacts);
  // Avoid duplicating the one-liner when the brief already opens with it.
  const showGlance =
    !!glance && (!narrative || !narrative.trim().startsWith(glance.slice(0, 40)));

  return (
    <div className="space-y-4">
      {showGlance ? (
        <Card title="At a glance">
          <p className="text-sm leading-relaxed text-muted-foreground">{glance}</p>
        </Card>
      ) : null}

      {artifacts.length > 0 ? (
        <div className="w-full space-y-2">
          <h2 className="text-sm font-semibold tracking-tight">Infographics</h2>
          <ChatArtifacts artifacts={artifacts} fullWidth />
        </div>
      ) : null}

      {showStrip ? (
        <Card
          title="Scorecard"
          action={
            card.scope ? (
              <Badge variant="secondary" className="rounded-full">
                {label(String(card.scope))}
              </Badge>
            ) : null
          }
        >
          <ScorecardStrip card={card} />
        </Card>
      ) : null}

      {narrative ? (
        <Card
          title="Decision note"
          action={
            skipped.length > 0 ? (
              <Badge variant="outline" className="rounded-full text-[10px]">
                {skipped.length} step{skipped.length === 1 ? "" : "s"} skipped
              </Badge>
            ) : null
          }
        >
          <div className="max-h-72 overflow-y-auto text-sm leading-relaxed">
            <Markdown>{narrative}</Markdown>
          </div>
        </Card>
      ) : null}

      {!card && !narrative && artifacts.length === 0 ? (
        <Card title="Result">
          <pre className="overflow-x-auto rounded-xl bg-muted/40 p-3 text-xs text-muted-foreground">
            {JSON.stringify(result, null, 2)}
          </pre>
        </Card>
      ) : null}
    </div>
  );
}

export function isMonthlyReport(result: unknown): result is ReportDoc {
  return (
    !!result &&
    typeof result === "object" &&
    "headline" in result &&
    "meta" in result
  );
}

export function isWorkflowResult(result: unknown): result is WorkflowResultDoc {
  if (!result || typeof result !== "object") return false;
  const r = result as WorkflowResultDoc;
  return (
    "workflow" in r ||
    "steps" in r ||
    "artifacts" in r ||
    typeof r.summary === "string"
  );
}
