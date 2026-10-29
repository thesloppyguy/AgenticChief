export type Status = "green" | "amber" | "red" | null;

export interface KpiResult { key: string; score: number | null; excluded_reason: string | null }
export interface Pillar { pillar: string; score: number | null; status: Status; eligible_weight: number; kpis: KpiResult[] }
export interface Overall {
  score: number | null; status: Status; status_withheld: boolean; pillar_coverage: number; pillars: Pillar[];
}
export interface CompanyCard extends Overall { company_id: number; code: string; name: string }
export interface Scorecard {
  period: string; calc_version: string; thresholds: { green_min: number; amber_min: number }; scope: "group" | "restricted"; synthetic_data: boolean; no_source_kpis: string[];
  group: Overall & { companies_in_scope: number; companies_with_data: number };
  companies: CompanyCard[];
}
export interface Drilldown {
  period: string; pillar: string;
  kpis: {
    key: string; weight: number; direction: "higher" | "lower"; target: number;
    group_achievement: number | null; group_score: number | null; group_excluded_reason: string | null;
    coverage: number; no_source: boolean;
    companies: { company_id: number; code: string; achievement: number | null; score: number | null; excluded_reason: string | null }[];
  }[];
}
export interface KpiDef { key: string; pillar: string; weight: number; direction: string; target: number; manual: boolean }
export interface KpiCatalog { pillar_weights: Record<string, number>; kpis: KpiDef[] }

export interface SourceStatus {
  source: string; label: string; mode: "live" | "stub" | "disabled" | "registry"; live_enabled: boolean;
  kpis: string[]; stub_fixture: boolean; no_source_kpis: string[]; taken_over_by_registry?: string[]; data_origin?: string | null;
  last_run: null | { period: string; status: string; mode: string; companies_ok: number; companies_failed: number; records_written: number; finished_at: string | null };
}

export interface AlertItem {
  id: number; kind: string; severity: "low" | "medium" | "high" | "urgent"; entity: string; company_id: number | null; period: string;
  title: string; detail: { weakest_pillars?: { pillar: string; score: number }[]; previous_status?: string | null; synthetic?: boolean } | null;
  created_at: string; read: boolean;
}
export interface Approval {
  id: number; action: string; risk: string; summary: string; status: string; requested_by: string; via: string;
  args: Record<string, unknown>; context: { reason?: string } | null; created_at: string;
  decided_by: string | null; decision_comment: string | null; result: Record<string, unknown> | null;
  events?: { at: string; actor: string; event: string; comment: string | null }[];
}
export interface ActionDef { key: string; risk: string; description: string; group_wide_only: boolean }
export interface UnreadSummary { alerts: number; approvals_pending: number }

export interface RunSummary { id: number; workflow: string; period: string; status: string; error: string | null; requested_by: string; created_at: string; finished_at: string | null }
export interface RunDetail extends RunSummary {
  steps: { key: string; label: string; done: boolean }[];
  events: { seq: number; at: string; step: string; status: string; message: string }[];
  result: ReportDoc | null;
}
export interface SnapshotRow { id: number; kind: string; period: string; calc_version: string; content_hash: string | null; run_id: number | null; created_by: string; created_at: string }
export interface ReportDoc {
  meta: { period: string; previous_period: string | null; calc_version: string; generated_at: string; generated_by: string; synthetic_data: boolean; companies_in_scope: number; companies_with_data: number };
  headline: {
    group_score: number | null; group_status: Status; previous_group_score: number | null; delta: number | null; coverage_pct: number;
    pillars: { pillar: string; score: number | null; status: Status; previous: number | null; delta: number | null }[];
    distribution: { green: number; amber: number; red: number; none: number };
  };
  movers: { improved: { code: string; score: number; previous: number; delta: number }[]; declined: { code: string; score: number; previous: number; delta: number }[] };
  attention: { red_count: number; newly_red: string[]; red: { code: string; score: number; weakest_pillars: { pillar: string; score: number }[] }[] };
  exceptions: { missing: { kpi: string; missing_count: number; sample: string[] }[]; no_source: string[]; not_due: string[]; low_coverage: { count: number }; ingestion_problems: { source: string; status: string; failed: number }[] };
  lineage: { sources: { source: string; label: string; mode: string; last_run: null | { status: string; companies_ok: number; companies_failed: number } }[]; data_origin: Record<string, number> };
  commentary: { text: string; method: "ai" | "template"; issues: string[] };
  caveats: string[];
}

export interface ConnectionRow {
  id: number; slug: string; name: string; type: "mcp" | "api" | "function"; config: Record<string, unknown>; active: boolean;
  health_status: "unknown" | "healthy" | "unhealthy"; health_detail: string | null; capability_count: number; last_discovered_at: string | null;
}
export interface CapabilityRow {
  id: number; connection_id: number; key: string; name: string; description: string; risk: string; risk_overridden: boolean;
  version: number; validated_version: number | null; published_version: number | null; lifecycle: string; permissions?: string[];
  validation: { ok: boolean; checks: { name: string; ok: boolean; detail: string; skipped: boolean }[] } | null;
}
export interface CapabilityDetail extends CapabilityRow {
  input_schema: Record<string, unknown>; output_schema: Record<string, unknown> | null; kpis_using_it: string[];
  versions: { version: number; validated: boolean; risk: string; published: boolean }[];
}
export interface MappingRow {
  id: number; kpi_key: string; capability_id: number; capability_key: string | null; field_map: Record<string, string>;
  arg_template: Record<string, string>; status: string; score: number; reasons: string[] | null; approved_by: string | null;
}
export interface DiscoverSummary { added: string[]; changed: string[]; unchanged: string[]; removed: string[]; impacts: { capability: string; change: string; kpis: string[] }[] }

export interface Rules {
  pillar_weights: Record<string, number>; green_min: number; amber_min: number; score_cap: number | null;
  zero_lower_is_better_score: number; missing_ic_policy: "exclude" | "zero"; min_coverage_for_status: number; prorate_cumulative: boolean;
  kpi_overrides: Record<string, { weight: number | null; target: number | null }>;
}
export interface ConfigVersion { version: number; status: "draft" | "active" | "superseded"; rules: Rules; note: string; created_by: string; created_at: string; activated_by: string | null }
export interface ConfigOverview { active: { version: number; rules: Rules; built_in: boolean }; versions: ConfigVersion[] }
export interface ConfigPreview {
  period: string; companies_changing_status: number;
  active: { group_score: number | null; group_status: Status; distribution: Record<string, number> };
  draft: { group_score: number | null; group_status: Status; distribution: Record<string, number> };
  examples: { code: string; from: Status; to: Status; score_from: number | null; score_to: number | null }[];
}

export interface KpiCatalogRow { key: string; pillar: string; weight: number; target: number; default_weight: number; default_target: number; direction: string; manual: boolean; target_steps: unknown[] }

export interface LiveAlert { id: number; kind: string; severity: "low" | "medium" | "high" | "urgent"; title: string; entity: string; company_id: number | null; period: string }
export interface AlertPrefs { min_severity: string; muted_kinds: string[]; quiet_start: string | null; quiet_end: string | null; tz: string; known_kinds: string[]; severities: string[] }

export interface MockStatus {
  companies: number; generated: number; ai: number; fallback: number; model: string; token_configured: boolean; ai_configured: boolean; fallback_allowed: boolean;
  job: { running: boolean; started_at: string | null; finished_at: string | null; done: number; result: { ai?: number; fallback?: number; failed?: string[]; notes?: string[]; error?: string } | null };
}
