import { chemicalClassLabel, compactText, formatNumber, humanStage, readableFeatureList, readableToken, stripBackendLanguage } from './format';
import type { Aim3Row, Aim4Row, ExplanationView, ReadableReport, RecommendationCard, TargetInsight } from './types';

export const DEFAULT_CAVEATS = [
  'Use as a research screening hypothesis only.',
  'Do not treat this as a formulation, dose, field-use, safety, or regulatory recommendation.',
  'Confirm target activity, crop tolerance, toxicity, environmental behavior, and efficacy in appropriate assays before any practical claim.'
];

function text(value: unknown, fallback = 'Not specified'): string {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

function score(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function hasKnownTarget(row: Aim3Row | Aim4Row): boolean {
  return Boolean((row as Aim3Row).high_confidence_known_target_label || row.known_inhibitor_classes || row.evidence_class?.includes('real'));
}

export function evidenceStrength(row: Aim4Row): RecommendationCard['evidenceStrength'] {
  const s = score(row.optimization_objective);
  const suitability = score(row.intervention_suitability_score);
  const synergy = score(row.synergy_group_score);
  if (s >= 0.55 || suitability >= 0.55 || synergy >= 0.8 || hasKnownTarget(row)) return 'Strong';
  if (s >= 0.4 || suitability >= 0.4 || synergy >= 0.55) return 'Moderate';
  return 'Exploratory';
}

export function targetPriority(row: Aim3Row): TargetInsight['priority'] {
  const s = score(row.critical_transition_score);
  if (row.high_confidence_known_target_label || s >= 0.55) return 'High interest';
  if (s >= 0.35) return 'Medium interest';
  return 'Exploratory';
}

function evidencePhrase(row: Aim4Row): string {
  const features = readableFeatureList(row.synergy_match_schema ?? row.match_schema, 3);
  if (features.length) return features.join(', ');
  if (row.known_inhibitor_classes) return readableToken(row.known_inhibitor_classes);
  return 'combined target, chemical-feature, and portfolio-diversity evidence';
}

export function toRecommendationCard(row: Aim4Row, index = 0): RecommendationCard {
  const target = text(row.target_enzyme, 'Unlisted target');
  const family = text(row.target_family, 'Target family not listed');
  const stage = humanStage(row.stage);
  const compoundA = text(row.compound_a, 'Compound A');
  const compoundB = text(row.compound_b, 'Compound B');
  const classLabel = chemicalClassLabel(row.phytochemical_class_pair);
  const inhibitors = row.known_inhibitor_classes ? readableToken(row.known_inhibitor_classes) : '';
  const strength = evidenceStrength(row);
  const support = evidencePhrase(row);

  return {
    id: `${target}-${compoundA}-${compoundB}-${index}`,
    target,
    targetFamily: family,
    stage,
    compounds: [compoundA, compoundB],
    scoreLabel: formatNumber(row.optimization_objective, 2),
    evidenceStrength: strength,
    riskLevel: strength === 'Strong' ? 'Review carefully' : 'Validation required',
    classLabel,
    shortReason: `A candidate pair for ${target} in ${stage.toLowerCase()}. Review it as a screening lead, not as a ready-to-use product.`,
    biologicalReason: `${target} is grouped with ${family} and appears in a growth-stage context relevant to ${stage.toLowerCase()}. ${inhibitors ? `The available evidence also overlaps with ${inhibitors}.` : 'The biological link should be checked with target-specific assays.'}`,
    chemicalReason: `The pair combines ${compactText(compoundA, 64)} with ${compactText(compoundB, 64)}. The class pattern is ${classLabel}.`,
    synergyReason: `Pairing support is based on ${support}. This is a hypothesis for follow-up screening, not measured synergy.`,
    caveat: DEFAULT_CAVEATS[2],
    validationSteps: [
      'Confirm enzyme-level inhibition in a controlled biochemical assay.',
      'Compare crop and weed response before making any selectivity claim.',
      'Run toxicity and environmental persistence checks before any practical development decision.'
    ],
    raw: row
  };
}

export function toTargetInsight(row: Aim3Row, index = 0): TargetInsight {
  const name = text(row.enzyme_name, 'Unlisted target');
  const family = text(row.enzyme_family, 'Family not listed');
  const stage = humanStage(row.stage_assigned);
  const priority = targetPriority(row);
  const known = row.high_confidence_known_target_label || row.herbicide_site_of_action;
  const basis = known
    ? `This target has known target-class support and appears in a ${stage.toLowerCase()} context.`
    : `This target appears biologically relevant in the available ${stage.toLowerCase()} evidence and should be treated as exploratory.`;
  return {
    id: `${name}-${index}`,
    name,
    family,
    stage,
    priority,
    reason: basis,
    biology: row.herbicide_site_of_action ? `Connected target biology: ${readableToken(row.herbicide_site_of_action)}.` : `Relevant as a ${family} enzyme during ${stage.toLowerCase()}.`,
    validationNeed: 'Validate target effect, crop tolerance, toxicity, and environmental behavior before any practical claim.',
    raw: row
  };
}

export function uniqueOptions<T>(rows: T[], getter: (row: T) => unknown, limit = 80): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    const value = text(getter(row), '').trim();
    if (value) seen.add(value);
    if (seen.size >= limit) break;
  }
  return Array.from(seen).sort((a, b) => a.localeCompare(b));
}

export function filterRecommendations(cards: RecommendationCard[], query: string, target: string, stage: string, strength: string): RecommendationCard[] {
  const q = query.trim().toLowerCase();
  return cards.filter((card) => {
    const hay = `${card.target} ${card.targetFamily} ${card.stage} ${card.classLabel} ${card.compounds.join(' ')} ${card.evidenceStrength}`.toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (target && card.target !== target && card.targetFamily !== target) return false;
    if (stage && card.stage !== stage) return false;
    if (strength && card.evidenceStrength !== strength) return false;
    return true;
  });
}

export function filterTargets(cards: TargetInsight[], query: string, family: string, stage: string, priority: string): TargetInsight[] {
  const q = query.trim().toLowerCase();
  return cards.filter((card) => {
    const hay = `${card.name} ${card.family} ${card.stage} ${card.priority}`.toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (family && card.family !== family) return false;
    if (stage && card.stage !== stage) return false;
    if (priority && card.priority !== priority) return false;
    return true;
  });
}

function pickMainFinding(raw: Record<string, unknown> | null | undefined): string {
  const findings = (((raw?.run_summary as Record<string, unknown> | undefined)?.main_findings ?? (raw?.sections as Record<string, unknown> | undefined)?.run_summary) as unknown) as unknown[] | undefined;
  if (!Array.isArray(findings)) return '';
  return stripBackendLanguage(findings.map(String).filter(Boolean).join(' '));
}

export function buildRunExplanation(recommendations: RecommendationCard[], targets: TargetInsight[], raw?: Record<string, unknown> | null): ExplanationView {
  const topPair = recommendations[0];
  const topTarget = targets[0];
  const backendFinding = pickMainFinding(raw);
  return {
    title: 'Latest screening interpretation',
    lead: topPair
      ? `PESI has candidate pairs ready for review. The first recommendation links ${topPair.compounds[0]} + ${topPair.compounds[1]} with ${topPair.target}.`
      : 'PESI can summarize the latest screening run once candidate-pair outputs are available.',
    sections: [
      {
        title: 'What the result is useful for',
        body: 'Use the output to choose which enzyme targets and compound pairs deserve deeper biochemical review. It is designed for prioritization, not for field-use decisions.'
      },
      {
        title: 'Most visible target signal',
        body: topTarget ? `${topTarget.name} is currently the most prominent target card. ${topTarget.reason}` : 'No target cards were loaded yet.'
      },
      {
        title: 'Most visible candidate pair',
        body: topPair ? `${topPair.compounds[0]} + ${topPair.compounds[1]} is presented as a ${topPair.evidenceStrength.toLowerCase()} screening lead for ${topPair.target}.` : 'No candidate pairs were loaded yet.'
      },
      ...(backendFinding ? [{ title: 'Backend artifact summary, translated', body: backendFinding }] : [])
    ],
    caveats: DEFAULT_CAVEATS
  };
}

export function buildRecommendationExplanation(card: RecommendationCard, raw?: Record<string, unknown> | null): ExplanationView {
  const translated = stripBackendLanguage((raw?.rationale ?? raw?.synergy_basis ?? '') as string);
  return {
    title: `${card.compounds[0]} + ${card.compounds[1]}`,
    lead: `This is a review candidate for ${card.target} during ${card.stage.toLowerCase()}.`,
    sections: [
      { title: 'Why this target matters', body: card.biologicalReason },
      { title: 'Why this pair was grouped together', body: card.chemicalReason },
      { title: 'What supports the pairing', body: translated || card.synergyReason },
      { title: 'What to validate next', body: card.validationSteps.join(' ') }
    ],
    caveats: DEFAULT_CAVEATS
  };
}

export function buildTargetExplanation(target: TargetInsight, raw?: Record<string, unknown> | null): ExplanationView {
  const translated = stripBackendLanguage((raw?.why_ranked ?? raw?.herbicide_biology ?? '') as string);
  return {
    title: target.name,
    lead: `This target is marked as ${target.priority.toLowerCase()} in the current evidence set.`,
    sections: [
      { title: 'Biological signal', body: target.biology },
      { title: 'Why it appears in the review list', body: translated || target.reason },
      { title: 'Interpretation boundary', body: 'This is a target-prioritization signal. It does not establish crop safety, weed selectivity, or practical efficacy.' },
      { title: 'What to validate next', body: target.validationNeed }
    ],
    caveats: DEFAULT_CAVEATS
  };
}

export function buildReadableReport(params: {
  crop: string;
  weed: string;
  stage: string;
  recommendations: RecommendationCard[];
  targets: TargetInsight[];
  reportType: 'summary' | 'full';
}): ReadableReport {
  const { crop, weed, stage, recommendations, targets, reportType } = params;
  const topRecs = recommendations.slice(0, reportType === 'summary' ? 3 : 8);
  const topTargets = targets.slice(0, reportType === 'summary' ? 3 : 6);
  return {
    title: 'PESI screening interpretation report',
    intro: `Scenario: ${crop || 'crop not specified'} vs ${weed || 'weed not specified'} at ${stage || 'growth stage not specified'}. The report summarizes review candidates and target signals from the latest PESI outputs.`,
    sections: [
      {
        title: 'Purpose of this report',
        body: 'This report helps a researcher decide which enzyme targets and compound pairs are worth follow-up review. It intentionally avoids backend validation language, row counts, terminal logs, and internal benchmark phrasing.'
      },
      {
        title: 'Scenario framing',
        body: `Interpret all candidates in the context of ${crop || 'the selected crop'} and ${weed || 'the selected weed'} during ${stage || 'the selected growth stage'}. A good screening lead still needs crop-response and weed-response validation.`
      },
      {
        title: 'Candidate-pair summary',
        body: topRecs.length ? topRecs.map((card, i) => `${i + 1}. ${card.compounds[0]} + ${card.compounds[1]} for ${card.target}: ${card.evidenceStrength.toLowerCase()} review lead.`).join('\n') : 'No candidate-pair results were available.'
      },
      {
        title: 'Target summary',
        body: topTargets.length ? topTargets.map((target, i) => `${i + 1}. ${target.name}: ${target.priority.toLowerCase()} target signal during ${target.stage.toLowerCase()}.`).join('\n') : 'No target results were available.'
      },
      {
        title: 'Required validation before use',
        body: 'Prioritize enzyme inhibition assays, crop/weed comparative response testing, toxicity review, environmental persistence review, and replication across growth stages before any practical development decision.'
      }
    ],
    recommendations: topRecs,
    targets: topTargets,
    caveats: DEFAULT_CAVEATS
  };
}
