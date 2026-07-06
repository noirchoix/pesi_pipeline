export function formatNumber(value: unknown, digits = 3): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value === null || value === undefined || value === '' ? '—' : String(value);
  if (Number.isInteger(n)) return n.toLocaleString();
  if (Math.abs(n) >= 1000) return n.toLocaleString();
  return n.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
}

export function titleCase(value: string | undefined | null): string {
  if (!value) return '—';
  return value
    .replace(/aim\s*([0-9])/gi, 'Aim $1')
    .replace(/[_-]+/g, ' ')
    .replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1));
}

export function compactText(value: unknown, max = 80): string {
  const text = value === null || value === undefined || value === '' ? '—' : String(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function labelFor(value: string | undefined | null): string {
  if (!value) return '—';
  const labels: Record<string, string> = {
    target_enzyme: 'Target',
    target_family: 'Target family',
    stage: 'Growth stage',
    stage_assigned: 'Growth stage',
    enzyme_name: 'Target',
    enzyme_family: 'Family',
    compound_a: 'Compound A',
    compound_b: 'Compound B',
    optimization_objective: 'Review fit',
    intervention_suitability_score: 'Candidate fit',
    high_confidence_known_target_label: 'Known target signal',
    high_confidence_target_basis: 'Why it matters',
    critical_transition_score: 'Priority score',
    phytochemical_class_pair: 'Chemical class pair',
    synergy_group_score: 'Pairing support',
    scenario_selectivity_margin: 'Selectivity margin',
    evidence_class: 'Evidence type',
    gate: 'Check',
    metric: 'Metric',
    value: 'Value',
    interpretation: 'Meaning'
  };
  return labels[value] ?? titleCase(value);
}

export function plainStatus(status: string | undefined | null): string {
  if (!status) return 'Unknown';
  if (status === 'passed') return 'Ready';
  if (status === 'succeeded') return 'Complete';
  if (status === 'failed') return 'Needs review';
  if (status === 'running') return 'Running';
  if (status === 'queued') return 'Queued';
  return titleCase(status);
}

export function humanStage(value: unknown): string {
  const text = value === null || value === undefined || value === '' ? '' : String(value);
  const labels: Record<string, string> = {
    germination: 'Germination',
    seedling_emergence: 'Seedling emergence',
    early_vegetative: 'Early vegetative growth',
    vegetative_expansion: 'Vegetative expansion',
    specialized_metabolism: 'Specialized metabolism',
    stress_response: 'Stress response',
    unassigned_stage: 'Unassigned stage'
  };
  return labels[text] ?? titleCase(text || 'Not listed');
}

export function readableList(values: unknown[], limit = 3): string {
  const clean = values.map((v) => compactText(v, 60)).filter((v) => v && v !== '—');
  if (clean.length === 0) return 'None listed';
  const head = clean.slice(0, limit).join(', ');
  return clean.length > limit ? `${head}, and ${clean.length - limit} more` : head;
}

export function readableToken(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'not listed';
  const raw = String(value);
  const mapped: Record<string, string> = {
    active_site_compatibility: 'active-site fit',
    functional_group_match: 'functional-group match',
    herbicide_target_atlas_match: 'known target-class support',
    known_inhibitor_class_similarity: 'similarity to known inhibitor classes',
    transition_state_mimicry: 'transition-state mimic pattern',
    known_inhibitor_like: 'known-inhibitor-like signal',
    transition_state_mimic_candidate: 'transition-state mimic candidate',
    phenolic_or_aromatic_hydroxyl: 'phenolic/aromatic hydroxyl group',
    transition_state_acidic_mimic: 'acidic transition-state mimic group',
    real_evidence_plus_model_inference: 'evidence-backed model inference',
    model_inference_with_real_compound_and_target_rule_evidence: 'artifact-backed model inference',
    core_transition_anchor_plus_atlas_match: 'growth-stage target evidence plus known target-class support',
    not_high_confidence: 'exploratory target signal'
  };
  return mapped[raw] ?? raw.replace(/\|\|/g, ' + ').replace(/[;_]+/g, ' ').replace(/\s+/g, ' ').trim();
}

export function readableFeatureList(value: unknown, limit = 4): string[] {
  if (!value) return [];
  return String(value)
    .split(/[;|]+/)
    .map((part) => readableToken(part.trim()))
    .filter((part) => part && part !== 'not listed')
    .slice(0, limit);
}

export function chemicalClassLabel(value: unknown): string {
  if (!value) return 'chemical class not listed';
  const labels: Record<string, string> = {
    organophosphonate_transition_state_mimic: 'phosphonate-like transition-state mimic',
    phenolic_acid_or_benzoate: 'phenolic acid / benzoate-like compound',
    organosulfur_sulfonate: 'organosulfur / sulfonate-like compound',
    flavonoid_polyphenol: 'flavonoid / polyphenol-like compound',
    quinone_redox_candidate: 'quinone-like redox-active compound',
    terpenoid_lipophilic: 'terpenoid / lipophilic compound',
    alkaloid_nitrogenous: 'alkaloid / nitrogen-containing compound',
    glycoside_or_sugar_conjugate: 'glycoside / sugar-conjugate',
    organic_acid_or_lactone: 'organic acid / lactone-like compound',
    unclassified_or_unknown: 'unclassified screening compound'
  };
  return String(value)
    .split('||')
    .map((part) => labels[part] ?? readableToken(part))
    .join(' + ');
}

export function stripBackendLanguage(value: unknown): string {
  if (!value) return '';
  return String(value)
    .replace(/Production gate status is passed with\s*\d+\/\d+\s*gates passing\.?/gi, '')
    .replace(/Aim\s*4\s*portfolio contains[^.]+\./gi, '')
    .replace(/Aim\s*\d+/gi, 'the screening run')
    .replace(/critical transition score:\s*[0-9.]+\.?/gi, '')
    .replace(/optimization objective\s*[0-9.]+\.?/gi, '')
    .replace(/with objective\s*[0-9.]+\.?/gi, '')
    .replace(/with score\s*[0-9.]+\.?/gi, '')
    .replace(/\brows?\b/gi, 'results')
    .replace(/[_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
