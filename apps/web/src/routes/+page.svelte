<script lang="ts">
  import { onMount } from 'svelte';
  import ResultRecommendationCard from '$components/ResultRecommendationCard.svelte';
  import ResultTargetCard from '$components/ResultTargetCard.svelte';
  import { activeRunId, api } from '$lib/api';
  import type { InferenceResults } from '$lib/types';

  let loading = true;
  let error = '';
  let data: InferenceResults | null = null;

  async function load() {
    loading = true;
    error = '';
    try {
      data = await api.inferenceResults(activeRunId(), 4);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  onMount(load);
</script>

<svelte:head><title>PESI | Plant Enzyme Inference</title></svelte:head>

<div class="page">
  <section class="hero panel">
    <div>
      <span class="eyebrow">Plant enzyme inference</span>
      <h1>Screen plant enzyme targets and candidate compound pairs.</h1>
      <p class="lede">Choose a crop/weed context, run the screening backend, review candidate pairs and enzyme targets, then generate readable scientific rationale.</p>
      <div class="row">
        <a class="primary" href="/analyze">Start new analysis</a>
        <a class="secondary" href="/results">Review latest results</a>
      </div>
    </div>
    <div class="hero-card">
      <span class="kicker">Typical workflow</span>
      <ol class="workflow-preview" aria-label="Typical PESI workflow">
        <li class="active"><span>01</span><strong>Set context</strong></li>
        <li><span>02</span><strong>Run screening</strong></li>
        <li><span>03</span><strong>Review results</strong></li>
        <li><span>04</span><strong>Explain & report</strong></li>
      </ol>
    </div>
  </section>

  <div class="notice section">
    <strong>Research screening only</strong>
    <p>Outputs are prioritization hypotheses. Validate biology, crop response, toxicity, and environmental behavior before any practical use.</p>
  </div>

  <section class="grid three section">
    <div class="help-card"><strong>New Analysis</strong><p>Set crop, weed, growth stage, and analysis goal before starting a run.</p></div>
    <div class="help-card"><strong>Results</strong><p>Review candidate pairs, target enzymes, scenario notes, evidence strength, and validation burden.</p></div>
    <div class="help-card"><strong>Explain / Report</strong><p>Generate readable rationale and export a scientific research summary without backend jargon.</p></div>
  </section>

  <section class="grid two section">
    <div>
      <div class="between">
        <h2>Candidate pairs ready for review</h2>
        <a class="secondary" href="/results">Open all</a>
      </div>
      <div class="stack">
        {#if loading}
          <div class="card muted">Loading latest recommendations…</div>
        {:else if error}
          <div class="error">{error}</div>
        {:else if data?.recommendations?.length}
          {#each data.recommendations.slice(0, 2) as rec}
            <ResultRecommendationCard item={rec} />
          {/each}
        {:else}
          <div class="card muted">No candidate-pair results are available yet. Start a new analysis.</div>
        {/if}
      </div>
    </div>
    <div>
      <div class="between">
        <h2>Important enzyme targets</h2>
        <a class="secondary" href="/results?view=targets">Explore targets</a>
      </div>
      <div class="stack">
        {#if data?.targets?.length}
          {#each data.targets.slice(0, 2) as target}
            <ResultTargetCard item={target} />
          {/each}
        {:else}
          <div class="card muted">Target insights will appear after outputs are available.</div>
        {/if}
      </div>
    </div>
  </section>
</div>

<style>
  .hero { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr); gap:1rem; align-items:stretch; }
  .hero-card { border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); padding:1rem; display:grid; align-content:center; gap:.85rem; min-width:0; }
  @media (max-width:900px){ .hero{grid-template-columns:1fr;} }
</style>
