// Mirrors the API response models (apps/api/src/pgmlens_api/schemas.py).

export type Severity = "low" | "medium" | "high" | "critical";
export type HealthStatus = "on_track" | "at_risk" | "off_track";
export type IssueStatus = "todo" | "in_progress" | "blocked" | "done";
export type ForecastStatus = "ok" | "complete" | "insufficient_data" | "not_converging";

export interface Finding {
  id: string;
  rule_id: string;
  rule_type: string;
  title: string;
  severity: Severity;
  message: string;
  action: string;
  issue_ids: string[];
  issue_keys: string[];
  milestone_ids: string[];
  metrics: Record<string, unknown>;
}

export interface Forecast {
  scope_id: string | null;
  scope_name: string;
  status: ForecastStatus;
  remaining: number;
  weeks_of_history: number;
  mean_weekly_throughput: number;
  mean_weekly_scope_growth: number;
  p50_date: string | null;
  p80_date: string | null;
  p95_date: string | null;
  due_date: string | null;
  on_time_probability: number | null;
  note: string;
  summary: string;
}

export interface ProgramHealth {
  status: HealthStatus;
  label: string;
  headline: string;
  reasons: string[];
  severity_counts: Record<Severity, number>;
}

export interface Stats {
  total: number;
  open: number;
  done: number;
  todo: number;
  in_progress: number;
  blocked: number;
  unassigned_open: number;
}

export interface ProgramSummary {
  id: string;
  name: string;
  description: string;
  as_of: string;
  health: ProgramHealth;
  stats: Stats;
  next_milestone: Forecast | null;
  top_risks: Finding[];
}

export interface Issue {
  id: string;
  key: string;
  title: string;
  status: IssueStatus;
  assignee: string | null;
  project_id: string;
  milestone_id: string | null;
  estimate: number | null;
  url: string | null;
  days_since_update: number;
  critical: boolean;
  waiting: boolean;
}

export interface Milestone {
  id: string;
  name: string;
  due_date: string | null;
  open_issues: number;
  total_issues: number;
}

export interface Edge {
  source: string;
  target: string;
  critical: boolean;
  unresolved: boolean;
}

export interface ProgramDetail {
  summary: ProgramSummary;
  analysis: {
    program: { id: string; name: string; description: string };
    as_of: string;
    health: ProgramHealth;
    stats: Stats;
    forecasts: Forecast[];
    findings: Finding[];
    graph: { critical_path: { issue_ids: string[]; length: number } };
  };
  issues: Issue[];
  milestones: Milestone[];
  projects: { id: string; key: string; name: string }[];
  graph: { nodes: string[]; edges: Edge[]; critical_path: string[] };
}

export interface BriefingClaim {
  text: string;
  fact_ids: string[];
}

export interface Briefing {
  program: string;
  as_of: string;
  source: "deterministic" | "llm";
  headline: string;
  sections: { title: string; claims: BriefingClaim[] }[];
  facts: { id: string; kind: string; text: string; action: string; evidence: string[] }[];
  warnings: string[];
}

export interface BriefingOut {
  briefing: Briefing;
  markdown: string;
}
