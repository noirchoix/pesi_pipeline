export type Gate = {
  gate: string;
  metric: string;
  operator: string;
  threshold: number;
  value: number | string | null;
  rationale: string;
  passed: boolean;
  status: 'passed' | 'failed' | string;
};

export type GateSummary = {
  status: string;
  passed_gates: number;
  total_gates: number;
  failed_gates: string[];
  gates: Gate[];
};

export type TableResponse<T = Record<string, unknown>> = {
  status: 'ok' | 'missing';
  path?: string;
  rows: T[];
  total_rows: number;
  limit: number;
  offset: number;
  columns: string[];
};

export type RunRecord = {
  run_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  request: Record<string, unknown>;
  output_dir: string;
  artifact_dir: string;
  log_path: string;
  error?: string | null;
};

export type ScenarioInput = {
  crop: string;
  weed: string;
  growth_stage: string;
};

export type InferenceOption = {
  value: string;
  label: string;
  description?: string;
};

export type InferenceOptions = {
  status: string;
  growth_stages: InferenceOption[];
  analysis_goals: InferenceOption[];
  example_scenarios: Array<{ crop: string; weed: string; stage: string }>;
  defaults: { crop: string; weed: string; growth_stage: string; goal: string; profile: string };
};

export type ProgressStep = {
  key: string;
  label: string;
  description: string;
  state: 'pending' | 'current' | 'complete' | 'error';
};

export type AnalysisProgress = {
  status: RunRecord['status'] | 'missing';
  run_id?: string;
  message: string;
  steps: ProgressStep[];
  error?: string | null;
  technical_log_available?: boolean;
};

export type Recommendation = {
  row_index: number;
  id: string;
  target: string;
  target_family: string;
  stage: string;
  compound_a: string;
  compound_b: string;
  compound_pair: [string, string];
  chemical_class: string;
  evidence_strength: string;
  short_reason: string;
  why_selected: string;
  biology_note: string;
  pairing_note: string;
  validation_note: string;
  risk_level: string;
  raw_scores?: Record<string, number | null>;
};

export type TargetInsight = {
  row_index: number;
  id: string;
  name: string;
  family: string;
  stage: string;
  priority: string;
  reason: string;
  biology_note: string;
  support_note: string;
  validation_note: string;
  raw_scores?: Record<string, number | null>;
};

export type ScenarioNote = { title: string; body: string };
export type SynergyNote = { row_index: number; target: string; stage: string; members: string[]; evidence_strength: string; note: string };

export type InferenceResults = {
  status: 'ok' | 'missing';
  run?: RunRecord | null;
  scenario: Partial<ScenarioInput>;
  recommendations: Recommendation[];
  targets: TargetInsight[];
  scenario_notes: ScenarioNote[];
  synergy_notes: SynergyNote[];
  filters: Record<string, string[]>;
  caveats: string[];
};

export type ExplanationSection = { title: string; body: string };

export type Explanation = {
  status: string;
  title: string;
  lead: string;
  sections: ExplanationSection[];
  caveats: string[];
  ai_source?: string;
  ai_status?: string;
  message?: string;
};

export type ReadableReport = {
  status: string;
  report_type: string;
  title: string;
  intro: string;
  sections: ExplanationSection[];
  recommendations: Recommendation[];
  targets: TargetInsight[];
  caveats: string[];
};

export type Aim3Row = Record<string, unknown>;
export type Aim4Row = Record<string, unknown>;
