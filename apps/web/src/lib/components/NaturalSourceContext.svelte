<script lang="ts">
  import type { FoodSourceRecord, NaturalSourceContext as SourceContext } from '$lib/types';
  import { formatNumber, titleCase } from '$lib/format';

  export let context: SourceContext;
  export let compoundA: string;
  export let compoundB: string;

  function sourceTitle(row: FoodSourceRecord): string {
    return row.food_name || row.food_name_scientific || 'Unnamed food record';
  }

  function evidenceLabel(row: FoodSourceRecord): string {
    const value = row.occurrence_evidence || row.compound_a_occurrence_evidence || 'reported occurrence';
    return titleCase(value);
  }
</script>

<section class="source-context" aria-labelledby="source-context-title">
  <div class="between compact-head">
    <div>
      <span class="kicker">Natural source context</span>
      <h4 id="source-context-title">Where the mapped compounds are reported</h4>
    </div>
    {#if context.shared_food_count > 0}
      <span class="status-pill strong">{context.shared_food_count} shared sources</span>
    {:else if context.compound_a_sources.length || context.compound_b_sources.length}
      <span class="status-pill warn">Individual sources only</span>
    {:else}
      <span class="status-pill">No mapped source</span>
    {/if}
  </div>

  {#if context.shared_sources.length}
    <div class="source-block">
      <strong>Reported for both compounds</strong>
      <div class="source-list">
        {#each context.shared_sources.slice(0, 5) as source}
          <article>
            <span>{sourceTitle(source)}</span>
            <small>{source.food_group || 'Food record'} · {formatNumber(source.shared_source_confidence, 2)} confidence</small>
          </article>
        {/each}
      </div>
    </div>
  {/if}

  <div class="grid two source-columns">
    <div class="source-block">
      <strong>{compoundA}</strong>
      {#if context.compound_a_sources.length}
        <ul>
          {#each context.compound_a_sources.slice(0, 5) as source}
            <li><span>{sourceTitle(source)}</span><small>{evidenceLabel(source)}</small></li>
          {/each}
        </ul>
      {:else}
        <p class="muted small">No FoodDB occurrence was resolved for this compound.</p>
      {/if}
    </div>
    <div class="source-block">
      <strong>{compoundB}</strong>
      {#if context.compound_b_sources.length}
        <ul>
          {#each context.compound_b_sources.slice(0, 5) as source}
            <li><span>{sourceTitle(source)}</span><small>{evidenceLabel(source)}</small></li>
          {/each}
        </ul>
      {:else}
        <p class="muted small">No FoodDB occurrence was resolved for this compound.</p>
      {/if}
    </div>
  </div>

  <div class="notice compact source-caveat">
    <strong>Occurrence is context, not a use recommendation</strong>
    <p>{context.caveat}</p>
  </div>
</section>

<style>
  .source-context { display:grid; gap:.8rem; }
  .compact-head { align-items:flex-start; }
  h4 { margin:.15rem 0 0; font-size:.98rem; }
  .source-block { border:1px solid var(--line); border-radius:14px; padding:.75rem; background:#fbfcfa; min-width:0; }
  .source-block > strong { display:block; margin-bottom:.45rem; overflow-wrap:anywhere; }
  .source-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.45rem; }
  .source-list article { border:1px solid var(--line); border-radius:11px; padding:.55rem; background:var(--surface); min-width:0; }
  .source-list span, li span { display:block; font-weight:760; overflow-wrap:anywhere; }
  .source-list small, li small { display:block; color:var(--muted); margin-top:.15rem; line-height:1.35; }
  ul { list-style:none; padding:0; margin:0; display:grid; gap:.42rem; }
  li { padding-bottom:.42rem; border-bottom:1px solid var(--line); }
  li:last-child { border-bottom:0; padding-bottom:0; }
  .source-caveat { margin-top:.1rem; }
  @media (max-width:620px){ .source-list,.source-columns{grid-template-columns:1fr;} }
</style>
