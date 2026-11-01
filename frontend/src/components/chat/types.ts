export type ArtifactTone = "good" | "alert" | "neutral" | string;

export type ArtifactHeadline = {
  label?: string;
  value?: number | string | null;
  unit?: string;
  note?: string;
  tone?: ArtifactTone;
  delta_pct?: number | null;
  delta_direction?: string;
};

export type ArtifactIssue = {
  rank?: number;
  title?: string;
  summary?: string;
  severity?: string;
  priority_label?: string;
  tags?: string[];
  flagged_by?: string[];
  recommendation?: string;
};

export type ArtifactDraft = {
  key?: string;
  title?: string;
  summary?: string;
  detail?: string;
  severity?: string;
  sla?: string;
  sla_style?: "pill" | "plain" | string;
  action?: string;
  propose_args?: Record<string, unknown>;
  drivers?: string[];
  channels?: string[];
  routes_to?: string[];
  insights?: string[];
  roi?: {
    programme_cost_cr?: number;
    avoided_hiring_premium_cr?: number;
    gap_closed_pct?: number;
    time_to_productivity_mo?: number;
    buy_time_to_productivity_mo?: number;
  };
};

export type ChatArtifact = {
  kind:
    | "kpi_bars"
    | "workforce_pulse"
    | "ic_compare"
    | "skills_demand_supply"
    | "succession_stack"
    | "scorecard_summary"
    | "action_drafts"
    | "table"
    | string;
  title?: string;
  subtitle?: string;
  source?: string;
  export_key?: string | null;
  schedule_key?: string | null;
  target?: number;
  overall?: number | null;
  status?: string;
  companies_in_scope?: number;
  companies_with_data?: number;
  pillar_coverage?: number;
  no_source_count?: number;
  stats?: ArtifactHeadline[];
  headline?: ArtifactHeadline[];
  narrative?: string;
  insights?: string[];
  capacity_insight?: string;
  mobility_insight?: string;
  exceptions?: {
    title?: string;
    score?: number | null;
    status?: string;
    detail?: string;
    action_key?: string;
  }[];
  items?: {
    label?: string;
    value?: number | null;
    unit?: string;
    status?: string;
    note?: string;
    tone?: ArtifactTone;
    target?: number | null;
    actual?: number | null;
    weight?: number | null;
    tags?: string[];
    delta_pct?: number | null;
    delta_direction?: string;
  }[];
  domains?: {
    label?: string;
    demand?: number;
    supply?: number;
    gap?: number;
    path?: string;
    insight?: string;
  }[];
  functions?: {
    function?: string;
    ready_now?: number;
    ready_1_2y?: number;
    no_successor?: number;
    is_new?: boolean;
  }[];
  pillars?: {
    key?: string;
    label?: string;
    score?: number | null;
    status?: string;
    weight?: number | null;
    kpi_count?: number;
  }[];
  issues?: ArtifactIssue[];
  drafts?: ArtifactDraft[];
  bench?: {
    role?: string;
    business?: string;
    ready_pct?: number;
    status?: string;
    successor?: string;
    development_move?: string;
    note?: string;
  }[];
  build_vs_buy?: {
    focus?: string;
    insight?: string;
    metrics?: { label?: string; build?: number; buy?: number; unit?: string }[];
  };
  mobility?: { label?: string; count?: number }[];
  capacity?: { from?: string; to?: string; candidates?: number }[];
  columns?: string[];
  rows?: unknown[][];
};

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  tools: string[];
  done: boolean;
  attachments?: string[];
  artifacts?: ChatArtifact[];
}

export interface AgentOption {
  value: string;
  label: string;
}
