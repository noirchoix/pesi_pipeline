<script lang="ts">
  import TargetStateReasoningPanel from '$components/TargetStateReasoningPanel.svelte';
  import { activeRunId, api } from '$lib/api';
  import type { EnzymeStateReasoning, TargetInsight } from '$lib/types';

  export let item: TargetInsight;
  export let showActions = true;

  let expanded = false;
  let loadingReasoning = false;
  let reasoning: EnzymeStateReasoning | null = null;
  let reasoningError = '';

  async function toggleReasoning() {
    expanded = !expanded;
    if (!expanded || reasoning || loadingReasoning) return;
    loadingReasoning = true;
    reasoningError = '';
    try {
      reasoning = await api.targetStateReasoning(item.id, activeRunId() || undefined, item.row_index);
    } catch (err) {
      reasoningError = err instanceof Error ? err.message : String(err);
    } finally {
      loadingReasoning = false;
    }
  }
</script>

<article class="card target-card">
  <header>
    <div>
      <span class="kicker">Enzyme target</span>
      <h3>{item.name}</h3>
      <p class="muted small">{item.reason}</p>
    </div>
    <span class="status-pill strong">{item.priority}</span>
  </header>

  <div class="meta-grid">
    <div><span>Family</span><strong>{item.family}</strong></div>
    <div><span>Growth stage</span><strong>{item.stage}</strong></div>
  </div>

  <p class="muted small">{item.biology_note}</p>

  <div class="row">
    <button class="secondary" type="button" aria-expanded={expanded} on:click={toggleReasoning}>
      {expanded ? 'Hide state reasoning' : 'View enzyme-state reasoning'}
    </button>
    {#if showActions}
      <a class="secondary" href={`/explain?kind=target&row=${item.row_index}`}>Explain this target</a>
    {/if}
  </div>

  {#if expanded}
    {#if loadingReasoning}
      <div class="reasoning-loading">Loading enzyme-state evidence…</div>
    {:else if reasoningError}
      <div class="error">{reasoningError}</div>
    {:else if reasoning}
      <TargetStateReasoningPanel {reasoning} />
    {:else}
      <div class="notice compact"><strong>State reasoning unavailable</strong><p>No state artifact was resolved for this target.</p></div>
    {/if}
  {/if}
</article>

<style>
  .reasoning-loading { border-top:1px solid var(--line); padding-top:.8rem; color:var(--muted); }
</style>
