<script lang="ts">
  import type { EnzymeStateReasoning } from '$lib/types';
  import { formatNumber, titleCase } from '$lib/format';
  export let reasoning: EnzymeStateReasoning;
</script>

<section class="state-panel stack">
  <div>
    <span class="kicker">Enzyme-state reasoning</span>
    <h4>{reasoning.why_state_matters || 'State rationale not resolved'}</h4>
  </div>
  <div class="grid three signal-grid">
    <article><span>Growth stage</span><strong>{titleCase(reasoning.growth_stage)}</strong></article>
    <article><span>Target class</span><strong>{titleCase(reasoning.target_class)}</strong></article>
    <article><span>Evidence source</span><strong>{reasoning.source || 'Not listed'}</strong></article>
  </div>
  <div class="grid three signal-grid">
    <article><span>Pathway essentiality</span><strong>{formatNumber(reasoning.evidence_signals?.pathway_essentiality, 3)}</strong></article>
    <article><span>Kinetic evidence</span><strong>{formatNumber(reasoning.evidence_signals?.kinetic_evidence, 3)}</strong></article>
    <article><span>Structure evidence</span><strong>{formatNumber(reasoning.evidence_signals?.structure_evidence, 3)}</strong></article>
    <article><span>Plant context</span><strong>{formatNumber(reasoning.evidence_signals?.plant_context, 3)}</strong></article>
    <article><span>Uncertainty penalty</span><strong>{formatNumber(reasoning.evidence_signals?.uncertainty_penalty, 3)}</strong></article>
    <article><span>Scenario margin</span><strong>{formatNumber(reasoning.scenario_selectivity?.selectivity_margin, 3)}</strong></article>
  </div>
  {#if reasoning.pathway_context?.length}
    <details class="disclosure">
      <summary>Pathway and reaction context</summary>
      <div class="inside stack">
        {#each reasoning.pathway_context as context}
          <article class="context-row">
            <strong>{titleCase(String(context.pathway || 'Pathway context'))}</strong>
            <p>{String(context.site_of_action || context.binding_logic || context.source || 'Context derived from PESI evidence artifacts.')}</p>
          </article>
        {/each}
      </div>
    </details>
  {/if}
  <div class="notice compact"><strong>Interpretation boundary</strong><p>{reasoning.limitations?.join(' ') || reasoning.limitation || 'This is a computational state model requiring target-specific validation.'}</p></div>
</section>

<style>
  .state-panel { border-top:1px solid var(--line); padding-top:.85rem; }
  h4 { margin:.15rem 0 0; font-size:.98rem; line-height:1.45; }
  .signal-grid article { border:1px solid var(--line); border-radius:12px; padding:.65rem; background:#fbfcfa; min-width:0; }
  .signal-grid span { display:block; color:var(--subtle); text-transform:uppercase; letter-spacing:.07em; font-size:.67rem; font-weight:850; }
  .signal-grid strong { display:block; margin-top:.2rem; overflow-wrap:anywhere; }
  .context-row { border:1px solid var(--line); border-radius:12px; padding:.65rem; background:#fbfcfa; }
  .context-row p { margin:.2rem 0 0; color:var(--muted); font-size:.88rem; }
</style>
