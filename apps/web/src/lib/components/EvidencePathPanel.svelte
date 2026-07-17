<script lang="ts">
  import NaturalSourceContext from '$components/NaturalSourceContext.svelte';
  import type { RecommendationEvidence } from '$lib/types';
  import { formatNumber, readableToken, titleCase } from '$lib/format';

  export let evidence: RecommendationEvidence;
  export let compoundA: string;
  export let compoundB: string;

  function asNumber(value: unknown): string {
    return formatNumber(value, 3);
  }
</script>

<div class="evidence-panel stack">
  <section>
    <span class="kicker">Evidence path</span>
    <h4>How this candidate moved through the evidence model</h4>
    <ol class="evidence-path">
      {#each evidence.path ?? [] as step}
        <li>
          <span class="step-number">{step.order}</span>
          <div>
            <strong>{step.label || titleCase(step.entity_type)}</strong>
            <p>{step.relationship}</p>
            <small>{step.source || 'Source not resolved'} · {titleCase(step.evidence_tier)}</small>
          </div>
        </li>
      {/each}
    </ol>
  </section>

  <NaturalSourceContext context={evidence.natural_source_context} {compoundA} {compoundB} />

  <details class="disclosure">
    <summary>Enzyme-state and scenario reasoning</summary>
    <div class="inside detail-grid">
      <article>
        <strong>Why this state matters</strong>
        <p>{evidence.enzyme_state_reasoning?.why_state_matters || 'State-specific rationale was not resolved.'}</p>
      </article>
      <article>
        <strong>Growth-stage signal</strong>
        <p>Peak {asNumber(evidence.enzyme_state_reasoning?.stage_signal?.trajectory_peak)} · curvature {asNumber(evidence.enzyme_state_reasoning?.stage_signal?.trajectory_curvature)} · transition position {asNumber(evidence.enzyme_state_reasoning?.stage_signal?.critical_transition_time)}</p>
      </article>
      <article>
        <strong>Scenario selectivity</strong>
        <p>Weed vulnerability {asNumber(evidence.scenario_selectivity?.weed_vulnerability)} · crop vulnerability {asNumber(evidence.scenario_selectivity?.crop_vulnerability)} · comparative margin {asNumber(evidence.scenario_selectivity?.selectivity_margin)}</p>
      </article>
      <article>
        <strong>Scientific boundary</strong>
        <p>{String(evidence.scenario_selectivity?.limitation || 'Scenario values are comparative screening proxies requiring controlled crop/weed assays.')}</p>
      </article>
    </div>
  </details>

  <details class="disclosure">
    <summary>Why these compounds were paired</summary>
    <div class="inside detail-grid">
      <article>
        <strong>Pairing rationale</strong>
        <p>{String(evidence.synergy_reasoning?.why_paired || 'The pair combines complementary inhibition-related signals for the same target context.')}</p>
      </article>
      <article>
        <strong>Functional signals</strong>
        <p>{(evidence.synergy_reasoning?.functional_signals as string[] | undefined)?.map(readableToken).join(', ') || 'No typed signals were listed.'}</p>
      </article>
      <article>
        <strong>Pairing support</strong>
        <p>{asNumber(evidence.synergy_reasoning?.pairing_support)} · inferred, not experimentally measured</p>
      </article>
      <article>
        <strong>Limitation</strong>
        <p>{String(evidence.synergy_reasoning?.limitation || 'Pair interaction requires assay validation.')}</p>
      </article>
    </div>
  </details>

  <details class="disclosure">
    <summary>Compound screening intelligence</summary>
    <div class="inside grid two">
      {#each [evidence.compound_intelligence?.compound_a, evidence.compound_intelligence?.compound_b] as compound}
        {#if compound}
          <article class="intelligence-card">
            <strong>{compound.compound}</strong>
            <p>{compound.why_allowed}</p>
            <dl>
              <div><dt>Priority basis</dt><dd>{readableToken(compound.why_prioritized)}</dd></div>
              <div><dt>Natural-product signal</dt><dd>{asNumber(compound.natural_product_evidence)}</dd></div>
              <div><dt>Availability signal</dt><dd>{asNumber(compound.availability_signal)}</dd></div>
              <div><dt>Hazard proxy</dt><dd>{asNumber(compound.hazard_proxy)}</dd></div>
              <div><dt>Persistence proxy</dt><dd>{asNumber(compound.persistence_proxy)}</dd></div>
            </dl>
            <small>{compound.limitation}</small>
          </article>
        {/if}
      {/each}
    </div>
  </details>

  <details class="disclosure">
    <summary>Confidence, assumptions, and assay priority</summary>
    <div class="inside stack">
      <p><strong>{evidence.confidence_and_limitations?.overall || 'Mixed evidence'}</strong></p>
      <div class="confidence-grid">
        <article><span>Direct evidence</span><ul>{#each evidence.confidence_and_limitations?.direct_evidence ?? [] as item}<li>{item}</li>{/each}</ul></article>
        <article><span>Model inference</span><ul>{#each evidence.confidence_and_limitations?.model_inference ?? [] as item}<li>{readableToken(item)}</li>{/each}</ul></article>
        <article><span>Proxy assumptions</span><ul>{#each evidence.confidence_and_limitations?.proxy_assumptions ?? [] as item}<li>{readableToken(item)}</li>{/each}</ul></article>
        <article><span>Weak or unsupported</span><ul>{#each evidence.confidence_and_limitations?.weak_or_unsupported_assumptions ?? [] as item}<li>{item}</li>{/each}</ul></article>
      </div>
      {#if evidence.assay_prioritization?.status === 'available'}
        <div class="notice compact">
          <strong>{evidence.assay_prioritization.label}</strong>
          <p>Relative simulated input band: {(evidence.assay_prioritization.relative_input_band ?? []).map((v) => asNumber(v)).join('–')}. {evidence.assay_prioritization.interpretation}</p>
        </div>
      {:else}
        <p class="muted small">No assay-priority simulation band was available for this candidate.</p>
      {/if}
      <p class="muted small">{evidence.confidence_and_limitations?.scientific_boundary}</p>
    </div>
  </details>
</div>

<style>
  .evidence-panel { border-top:1px solid var(--line); padding-top:.85rem; }
  h4 { margin:.15rem 0 .7rem; }
  .evidence-path { list-style:none; padding:0; margin:0; display:grid; gap:.5rem; }
  .evidence-path li { display:grid; grid-template-columns:auto minmax(0,1fr); gap:.65rem; align-items:start; border:1px solid var(--line); border-radius:13px; padding:.65rem; background:#fbfcfa; }
  .step-number { width:1.7rem; height:1.7rem; display:grid; place-items:center; border-radius:999px; background:var(--accent-soft); color:var(--accent-ink); font-size:.76rem; font-weight:850; }
  .evidence-path strong, .evidence-path p, .evidence-path small { display:block; overflow-wrap:anywhere; }
  .evidence-path p { margin:.12rem 0; color:var(--muted); font-size:.88rem; }
  .evidence-path small { color:var(--subtle); }
  .detail-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.55rem; }
  .detail-grid article, .intelligence-card { border:1px solid var(--line); border-radius:12px; padding:.7rem; background:#fbfcfa; min-width:0; }
  .detail-grid p, .intelligence-card p { margin:.25rem 0 0; color:var(--muted); line-height:1.5; font-size:.88rem; }
  dl { display:grid; gap:.35rem; margin:.65rem 0; }
  dl div { display:flex; justify-content:space-between; gap:.75rem; border-bottom:1px solid var(--line); padding-bottom:.3rem; }
  dt { color:var(--muted); }
  dd { margin:0; text-align:right; font-weight:760; }
  .confidence-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.55rem; }
  .confidence-grid article { border:1px solid var(--line); border-radius:12px; padding:.65rem; background:#fbfcfa; min-width:0; }
  .confidence-grid span { display:block; font-weight:800; margin-bottom:.35rem; }
  .confidence-grid ul { margin:0; padding-left:1rem; color:var(--muted); font-size:.86rem; line-height:1.45; }
  @media(max-width:680px){ .detail-grid,.confidence-grid{grid-template-columns:1fr;} }
</style>
