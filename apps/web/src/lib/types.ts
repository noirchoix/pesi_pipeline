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

export type FoodSourceRecord = {
  food_id?: number | string | null;
  food_public_id?: string | null;
  food_name?: string | null;
  food_name_scientific?: string | null;
  food_group?: string | null;
  food_subgroup?: string | null;
  occurrence_evidence?: string | null;
  source_confidence?: number | null;
  standard_content?: number | null;
  orig_content?: number | null;
  orig_unit?: string | null;
  citation_type?: string | null;
  evidence_class?: string | null;
  compound_a_occurrence_evidence?: string | null;
  compound_b_occurrence_evidence?: string | null;
  shared_source_confidence?: number | null;
};

export type NaturalSourceSummary = {
  status: string;
  shared_food_count: number;
  shared_quantified_food_count?: number;
  shared_source_confidence?: number | null;
  top_shared_sources: string[];
  compound_a_top_sources: string[];
  compound_b_top_sources: string[];
  evidence_class?: string | null;
  caveat?: string | null;
};

export type NaturalSourceContext = {
  status: string;
  shared_food_count: number;
  shared_quantified_food_count: number;
  shared_source_confidence?: number | null;
  shared_sources: FoodSourceRecord[];
  compound_a_sources: FoodSourceRecord[];
  compound_b_sources: FoodSourceRecord[];
  evidence_class?: string | null;
  caveat: string;
};

export type EvidencePathStep = {
  order: number;
  entity_type: string;
  label?: string | null;
  relationship: string;
  source?: string | null;
  evidence_tier: string;
};

export type EvidenceSignals = {
  kinetic_records?: number | null;
  kinetic_evidence?: number | null;
  structure_evidence?: number | null;
  plant_context?: number | null;
  pathway_essentiality?: number | null;
  uncertainty_penalty?: number | null;
};

export type EnzymeStateReasoning = {
  status: string;
  target: string;
  family?: string | null;
  growth_stage?: string | null;
  target_class?: string | null;
  why_state_matters?: string;
  trajectory?: { peak?: number | null; curvature?: number | null; critical_transition_time?: number | null };
  stage_signal?: { trajectory_peak?: number | null; trajectory_curvature?: number | null; critical_transition_time?: number | null };
  evidence_signals?: EvidenceSignals;
  scenario_selectivity?: {
    weed_vulnerability?: number | null;
    crop_vulnerability?: number | null;
    selectivity_margin?: number | null;
    stage_relevance?: string | null;
    evidence_class?: string | null;
    limitation?: string;
  };
  pathway_context?: Array<Record<string, unknown>>;
  source?: string | null;
  evidence_class?: string | null;
  limitation?: string;
  limitations?: string[];
};

export type CompoundIntelligence = {
  compound: string;
  why_allowed: string;
  why_prioritized: string;
  phytochemical_class?: string | null;
  functional_groups: string[];
  natural_product_evidence?: number | null;
  availability_signal?: number | null;
  hazard_proxy?: number | null;
  persistence_proxy?: number | null;
  intervention_suitability?: number | null;
  source?: string | null;
  evidence_class?: string | null;
  limitation: string;
};

export type AssayPrioritization = {
  status: string;
  label?: string;
  relative_input_band?: [number, number] | number[];
  simulated_max_inhibition?: number | null;
  model?: string;
  interpretation?: string;
  evidence_class?: string;
};

export type ConfidenceAndLimitations = {
  overall: string;
  direct_evidence: string[];
  model_inference: string[];
  proxy_assumptions: string[];
  weak_or_unsupported_assumptions: string[];
  scientific_boundary: string;
};

export type RecommendationEvidence = {
  status: string;
  recommendation_id?: string;
  summary?: string;
  path: EvidencePathStep[];
  enzyme_state_reasoning: EnzymeStateReasoning;
  scenario_selectivity: Record<string, unknown>;
  synergy_reasoning: Record<string, unknown>;
  compound_intelligence: { compound_a: CompoundIntelligence; compound_b: CompoundIntelligence };
  natural_source_context: NaturalSourceContext;
  assay_prioritization: AssayPrioritization;
  pathway_context: Array<Record<string, unknown>>;
  confidence_and_limitations: ConfidenceAndLimitations;
  source_artifacts: string[];
  caveats: string[];
  message?: string;
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
  natural_source_summary?: NaturalSourceSummary;
  evidence_path_available?: boolean;
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
  state_reasoning_available?: boolean;
  biology?: string;
  validationNeed?: string;
  raw?: Record<string, unknown>;
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
  food_source_mapping?: {
    status: string;
    recommended_match_coverage?: number | null;
    pairs_with_shared_sources?: number;
    caveat?: string | null;
  };
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
  evidence_path?: RecommendationEvidence;
  enzyme_state_reasoning?: EnzymeStateReasoning;
};

export type ReportInterpretationMode = {
  source: string;
  status: string;
  label: string;
  model?: string | null;
};

export type ReportPairGroup = {
  pair_id: string;
  compound_a: string;
  compound_b: string;
  pair_label: string;
  evidence_strength: string;
  chemical_class?: string | null;
  target_count: number;
  targets: Array<{
    target: string;
    target_family?: string | null;
    growth_stage?: string | null;
    evidence_strength?: string | null;
    enzyme_state_interpretation?: string;
    scenario_selectivity_interpretation?: string;
    pathway_context?: Array<Record<string, unknown>>;
    pairing_interpretation?: string;
    assay_priority?: Record<string, unknown>;
    validation_required?: string;
  }>;
  natural_source_context: {
    status: string;
    shared_source_count: number;
    shared_source_names: string[];
    interpretation: string;
    compound_a: Record<string, unknown>;
    compound_b: Record<string, unknown>;
    caveat: string;
  };
  evidence_provenance: Array<Record<string, unknown>>;
  confidence: Record<string, unknown>;
  assay_prioritization: {
    overall_priority: string;
    target_bands: Array<Record<string, unknown>>;
  };
};

export type ReadableReport = {
  status: string;
  report_type: string;
  title: string;
  intro: string;
  interpretation_mode?: ReportInterpretationMode;
  executive_summary?: {
    body?: string;
    key_findings?: string[];
    scenario_interpretation?: string;
  };
  sections: ExplanationSection[];
  pair_groups?: ReportPairGroup[];
  recommendations: Recommendation[];
  targets: TargetInsight[];
  recommendation_evidence?: RecommendationEvidence[];
  target_state_reasoning?: EnzymeStateReasoning[];
  food_source_mapping?: Record<string, unknown>;
  technical_appendix?: Record<string, unknown>;
  caveats: string[];
};

// Compatibility types retained for legacy adapter helpers that are not part of the primary UI flow.
export type RecommendationCard = {
  id: string;
  target: string;
  targetFamily: string;
  stage: string;
  compounds: [string, string];
  scoreLabel: string;
  evidenceStrength: 'Strong' | 'Moderate' | 'Exploratory';
  riskLevel: string;
  classLabel: string;
  shortReason: string;
  biologicalReason: string;
  chemicalReason: string;
  synergyReason: string;
  caveat: string;
  validationSteps: string[];
  raw: Record<string, unknown>;
};

export type ExplanationView = {
  title: string;
  lead: string;
  sections: ExplanationSection[];
  caveats: string[];
};

export type Aim3Row = Record<string, unknown>;
export type Aim4Row = Record<string, unknown>;
