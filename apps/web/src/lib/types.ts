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

export type DiversitySummary = {
  rows?: number;
  unique_targets?: number;
  unique_target_families?: number;
  unique_pairs?: number;
  unique_compounds?: number;
  unique_phytochemical_classes?: number;
  unique_phytochemical_class_pairs?: number;
  max_target_share?: number;
  max_pair_share?: number;
  max_individual_compound_share?: number;
  max_phytochemical_pair_share?: number;
  target_family_entropy_normalized?: number;
  stage_entropy_normalized?: number;
  phytochemical_class_entropy_normalized?: number;
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

export type Aim3Row = {
  enzyme_name?: string;
  enzyme_family?: string;
  stage_assigned?: string;
  critical_transition_score?: number;
  high_confidence_known_target_label?: number | boolean;
  high_confidence_target_basis?: string;
  herbicide_target_family?: string;
  herbicide_site_of_action?: string;
  known_inhibitor_classes?: string;
  evidence_class?: string;
};

export type Aim4Row = {
  target_enzyme?: string;
  target_family?: string;
  stage?: string;
  compound_a?: string;
  compound_b?: string;
  optimization_objective?: number;
  intervention_suitability_score?: number;
  phytochemical_class_pair?: string;
  known_inhibitor_classes?: string;
  synergy_group_score?: number;
  synergy_match_schema?: string;
  match_schema?: string;
  scenario_selectivity_margin?: number;
  crop_impact_estimate?: number;
  toxicity_hazard_proxy?: number;
  environmental_persistence_proxy?: number;
  evidence_class?: string;
  proxy_notes?: string;
};

export type RecommendationCard = {
  id: string;
  target: string;
  targetFamily: string;
  stage: string;
  compounds: [string, string];
  scoreLabel: string;
  evidenceStrength: 'Strong' | 'Moderate' | 'Exploratory';
  riskLevel: 'Review carefully' | 'Validation required';
  classLabel: string;
  shortReason: string;
  biologicalReason: string;
  chemicalReason: string;
  synergyReason: string;
  caveat: string;
  validationSteps: string[];
  raw: Aim4Row;
};

export type TargetInsight = {
  id: string;
  name: string;
  family: string;
  stage: string;
  priority: 'High interest' | 'Medium interest' | 'Exploratory';
  reason: string;
  biology: string;
  validationNeed: string;
  raw: Aim3Row;
};

export type ExplanationSection = {
  title: string;
  body: string;
};

export type ExplanationView = {
  title: string;
  lead: string;
  sections: ExplanationSection[];
  caveats: string[];
};

export type ReadableReport = {
  title: string;
  intro: string;
  sections: ExplanationSection[];
  recommendations: RecommendationCard[];
  targets: TargetInsight[];
  caveats: string[];
};
