export type Kind = "skill" | "agent";
export interface AssetSummary {
  id: number; key: string; name: string; description: string; lifecycle: string; version: number; published_version: number | null;
  builtin: boolean; tools: string[]; permissions: string[]; inputs: InputSchema | null; model: string | null;
}
export interface InputSchema { type: string; properties: Record<string, { type: string; enum?: string[]; default?: unknown; description?: string; minimum?: number; maximum?: number }>; required?: string[] }
export interface AssetDetail extends AssetSummary {
  definition?: Record<string, unknown>;
  validation?: { ok: boolean; checks: { name: string; ok: boolean; detail: string }[] } | null;
  versions?: { version: number; validated: boolean; eval_passed: boolean | null; published: boolean; created_by: string; eval_results: { cases: { case: string; passed: boolean; problems: string[] }[] } | null }[];
}
export const TEMPLATES: Record<Kind, object> = {
  skill: { instructions: "Describe what to do for {period}. Say which tools to call and how to present the answer.", inputs: { type: "object", properties: { period: { type: "string", description: "Fiscal period, YYYY-MM" } }, required: ["period"] }, tools: ["get_group_score"], output_format: "markdown", permissions: ["admin", "editor", "viewer"], eval_cases: [] },
  agent: { instructions: "Describe how this specialist should answer: its focus, tone, and what it must always state.", tools: ["get_group_score"], model: "default", permissions: ["admin", "editor", "viewer"], eval_cases: [] },
};
