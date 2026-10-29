import type { Status } from "./types";

// Names the scorecard uses: a plain title-casing would drop the "&" and "/".
const NAMES: Record<string, string> = {
  learning_development: "Learning & Development",
  engagement_wellness: "Engagement / Wellness",
};

export const label = (key: string) =>
  NAMES[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

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
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-800 ring-red-200",
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
