<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import ExplanationPanel from '$components/ExplanationPanel.svelte';
  import ResultRecommendationCard from '$components/ResultRecommendationCard.svelte';
  import ResultTargetCard from '$components/ResultTargetCard.svelte';
  import { activeRunId, api } from '$lib/api';
  import type { Explanation, InferenceResults } from '$lib/types';

  let data: InferenceResults | null = null;
  let explanation: Explanation | null = null;
  let loading = true;
  let explaining = false;
  let error = '';
  let kind = 'recommendation';
  let row = 0;

  $: runId = $page.url.searchParams.get('run') || activeRunId();
  $: selectedRecommendation = data?.recommendations?.find((item) => item.row_index === row) ?? data?.recommendations?.[0];
  $: selectedTarget = data?.targets?.find((item) => item.row_index === row) ?? data?.targets?.[0];

  async function load() {
    loading = true;
    error = '';
    try {
      kind = $page.url.searchParams.get('kind') || 'recommendation';
      row = Number($page.url.searchParams.get('row') ?? 0);
      data = await api.inferenceResults(runId, 60);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  async function explain() {
    explaining = true;
    error = '';
    explanation = null;
    try {
      if (kind === 'target') {
        explanation = await api.explainTarget({ run_id: runId || undefined, row_index: row });
      } else {
        explanation = await api.explainRecommendation({ run_id: runId || undefined, row_index: row });
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      explaining = false;
    }
  }

  onMount(load);
</script>

<div class="page">
  <header class="page-header">
    <span class="eyebrow">Explain</span>
    <h1>Generate readable scientific rationale.</h1>
    <p class="lede">Choose a recommendation or target, then ask PESI to explain the artifact-grounded rationale. If DeepSeek is configured server-side, the explanation is model-assisted; otherwise PESI uses a deterministic artifact-grounded fallback.</p>
  </header>

  {#if error}<div class="error">{error}</div>{/if}

  <section class="panel stack">
    <div class="explain-controls">
      <label class="field"><span>Explain</span><select bind:value={kind}><option value="recommendation">Candidate pair</option><option value="target">Enzyme target</option></select></label>
      <label class="field"><span>{kind === 'target' ? 'Target' : 'Candidate pair'}</span>
        <select bind:value={row}>
          {#if kind === 'target'}
            {#each data?.targets ?? [] as item}<option value={item.row_index}>{item.name}</option>{/each}
          {:else}
            {#each data?.recommendations ?? [] as item}<option value={item.row_index}>{item.compound_a} + {item.compound_b}</option>{/each}
          {/if}
        </select>
      </label>
      <div class="action-field"><button class="primary" disabled={explaining || loading} on:click={explain}>{explaining ? 'Explaining…' : 'Explain selection'}</button></div>
    </div>
  </section>

  <section class="result-layout section">
    <div class="stack">
      {#if kind === 'target'}
        {#if selectedTarget}<ResultTargetCard item={selectedTarget} showActions={false} />{/if}
      {:else}
        {#if selectedRecommendation}<ResultRecommendationCard item={selectedRecommendation} showActions={false} />{/if}
      {/if}
      {#if !explanation && !loading}
        <div class="notice compact"><strong>No explanation generated yet</strong><p>Select an item and click Explain selection.</p></div>
      {/if}
    </div>
    <ExplanationPanel {explanation} />
  </section>
</div>


<style>
  .explain-controls {
    display: grid;
    grid-template-columns: minmax(170px, 0.6fr) minmax(280px, 1.4fr) max-content;
    gap: 0.75rem;
    align-items: end;
    min-width: 0;
  }

  .explain-controls :global(.field),
  .explain-controls :global(select) {
    min-width: 0;
    width: 100%;
  }

  .explain-controls :global(select) {
    text-overflow: ellipsis;
  }

  .action-field {
    display: flex;
    align-items: flex-end;
    min-width: 0;
  }

  .action-field button {
    width: 100%;
    white-space: nowrap;
  }

  @media (max-width: 980px) {
    .explain-controls {
      grid-template-columns: minmax(160px, 0.7fr) minmax(0, 1.3fr);
    }

    .action-field {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: 680px) {
    .explain-controls {
      grid-template-columns: 1fr;
    }

    .action-field {
      grid-column: auto;
    }
  }
</style>
