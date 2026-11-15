import type { Status } from "./types";

// Names the scorecard uses: a plain title-casing would drop the "&" and "/".
const NAMES: Record<string, string> = {
  learning_development: "Learning & Development",
  engagement_wellness: "Engagement / Wellness",
};

/** Draft-action / programme keys — keep machine ids, show executive titles. */
const ACTION_NAMES: Record<string, string> = {
  capability_green_h2: "Green energy talent programme",
  retention_semi: "Semiconductor retention plan",
  atmp_leadership: "ATMP leadership — hire and develop",
  manager_effectiveness_bq: "Manager coaching for bottom quartile",
};

/** Workflow tool / agent refs shown on the Workflows page. */
const REF_NAMES: Record<string, string> = {
  "agent:chro": "HR Copilot",
  "agent:cfo": "Finance Copilot",
  "agent:ceo": "CEO Copilot",
  "agent:coo": "Operations Copilot",
  get_workforce_pulse: "Workforce pulse",
  list_draft_actions: "Pending actions",
  get_skills_gap: "Skills gap",
  get_succession_bench: "Succession bench",
  get_succession_coverage: "Succession coverage",
  get_dashboard_layout: "Home layout",
  get_scorecard_config: "Scorecard rules",
  draft_scorecard_config: "Draft scorecard rules",
  update_dashboard_layout: "Update Home layout",
  activate_scorecard_config: "Activate scorecard rules",
  launch_capability_program: "Launch talent programme",
  launch_retention_corrective: "Launch retention plan",
  send_directive: "Send directive",
};

export const label = (key: string) => {
  const k = key.trim();
  return (
    NAMES[k] ??
    ACTION_NAMES[k] ??
    REF_NAMES[k] ??
    k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
};

/** Prefer a short executive name for tools, agents, and draft keys. */
export const friendlyRef = (ref: string) => {
  const k = ref.trim();
  return REF_NAMES[k] ?? ACTION_NAMES[k] ?? label(k.replace(/^cap_/, ""));
};

// Short, distinct table headings (two pillars both start with "Talent").
export const PILLAR_SHORT: Record<string, string> = {
  talent_acquisition: "TA", performance_management: "PM", learning_development: "L&D",
  organizational_effectiveness: "OE", talent_management: "TM", engagement_wellness: "E/W", retention: "Ret",
};

export const fmt = (n: number | null | undefined, digits = 1) =>
  n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: digits });

export const STATUS_TEXT: Record<string, string> = {
  green: "On track", amber: "Needs attention", red: "Off track",
};

// Colour is never the only signal: every status also renders its text label.
export const STATUS_STYLE: Record<string, string> = {
  green: "border-success/30 bg-success/10 text-success",
  amber: "border-warning/30 bg-warning/10 text-warning",
  red: "border-destructive/30 bg-destructive/10 text-destructive",
};

export const currentPeriod = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export const statusOf = (s: Status) => (s ? STATUS_TEXT[s] : "No data");

// Why a KPI was left out of a score. "No source" is a connection gap, not a company's failure.
export const REASON_LABEL: Record<string, string> = {
  missing: "No value", not_due: "Not yet due", no_source: "No source",
};
export const reasonLabel = (r: string) => REASON_LABEL[r] ?? r;
