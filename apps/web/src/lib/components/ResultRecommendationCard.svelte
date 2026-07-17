<script lang="ts">
  import EvidencePathPanel from '$components/EvidencePathPanel.svelte';
  import { activeRunId, api } from '$lib/api';
  import type { Recommendation, RecommendationEvidence } from '$lib/types';

  export let item: Recommendation;
  export let showActions = true;

  let expanded = false;
  let loadingEvidence = false;
  let evidence: RecommendationEvidence | null = null;
  let evidenceError = '';

  async function toggleEvidence() {
    expanded = !expanded;
    if (!expanded || evidence || loadingEvidence) return;
    loadingEvidence = true;
    evidenceError = '';
    try {
      evidence = await api.recommendationEvidence(item.id, activeRunId() || undefined, item.row_index);
    } catch (err) {
      evidenceError = err instanceof Error ? err.message : String(err);
    } finally {
      loadingEvidence = false;
    }
  }
</script>

<article class="card recommendation-card">
  <header>
    <div>
      <span class="kicker">Candidate pair</span>
      <h3>{item.compound_a} + {item.compound_b}</h3>
      <p class="muted small">{item.short_reason}</p>
    </div>
    <span class="status-pill strong">{item.evidence_strength}</span>
  </header>

  <div class="meta-grid">
    <div><span>Target</span><strong>{item.target}</strong></div>
    <div><span>Growth stage</span><strong>{item.stage}</strong></div>
    <div><span>Target class</span><strong>{item.target_family}</strong></div>
    <div><span>Chemical pattern</span><strong>{item.chemical_class}</strong></div>
  </div>

  <p class="muted small">{item.why_selected}</p>

  {#if item.natural_source_summary}
    <div class="source-preview">
      <span>Natural source context</span>
      {#if item.natural_source_summary.top_shared_sources.length}
        <strong>Both mapped compounds are reported in {item.natural_source_summary.top_shared_sources.join(', ')}.</strong>
      {:else if item.natural_source_summary.compound_a_top_sources.length || item.natural_source_summary.compound_b_top_sources.length}
        <strong>Individual food-source records are available; no shared source is shown in the current mapping.</strong>
      {:else}
        <strong>No FoodDB source occurrence was resolved for this pair.</strong>
      {/if}
    </div>
  {/if}

  <div class="row actions">
    <button class="secondary" type="button" aria-expanded={expanded} on:click={toggleEvidence}>
      {expanded ? 'Hide evidence' : 'View evidence & source context'}
    </button>
    {#if showActions}
      <a class="secondary" href={`/explain?kind=recommendation&row=${item.row_index}`}>Explain this pair</a>
      <a class="ghost" href="/reports">Add to report</a>
    {/if}
  </div>

  {#if expanded}
    {#if loadingEvidence}
      <div class="evidence-loading">Loading evidence path and source context…</div>
    {:else if evidenceError}
      <div class="error">{evidenceError}</div>
    {:else if evidence}
      <EvidencePathPanel {evidence} compoundA={item.compound_a} compoundB={item.compound_b} />
    {:else}
      <div class="notice compact"><strong>Evidence not available</strong><p>No evidence-path artifact could be loaded for this recommendation.</p></div>
    {/if}
  {/if}
</article>

<style>
  .source-preview { border:1px solid var(--line); border-radius:12px; padding:.65rem; background:var(--surface-soft); display:grid; gap:.18rem; min-width:0; }
  .source-preview span { color:var(--subtle); text-transform:uppercase; letter-spacing:.08em; font-size:.68rem; font-weight:850; }
  .source-preview strong { font-size:.86rem; line-height:1.45; overflow-wrap:anywhere; }
  .actions { align-items:center; }
  .evidence-loading { border-top:1px solid var(--line); padding-top:.8rem; color:var(--muted); }
</style>
