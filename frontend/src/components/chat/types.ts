export type ChatArtifact = {
  kind:
    | "kpi_bars"
    | "ic_compare"
    | "skills_demand_supply"
    | "succession_stack"
    | "scorecard_summary"
    | "table"
    | string;
  title?: string;
  source?: string;
  export_key?: string | null;
  schedule_key?: string | null;
  items?: { label?: string; value?: number | null; unit?: string; status?: string }[];
  domains?: {
    label?: string;
    demand?: number;
    supply?: number;
    gap?: number;
    path?: string;
  }[];
  functions?: {
    function?: string;
    ready_now?: number;
    ready_1_2y?: number;
    no_successor?: number;
  }[];
  pillars?: {
    key?: string;
    label?: string;
    score?: number | null;
    status?: string;
  }[];
  overall?: number | null;
  status?: string;
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
