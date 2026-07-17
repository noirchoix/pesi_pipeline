<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import ResultRecommendationCard from '$components/ResultRecommendationCard.svelte';
  import ResultTargetCard from '$components/ResultTargetCard.svelte';
  import { activeRunId, api } from '$lib/api';
  import type { InferenceResults, Recommendation, TargetInsight } from '$lib/types';

  let data: InferenceResults | null = null;
  let loading = true;
  let error = '';
  let view = 'pairs';
  let query = '';
  let target = '';
  let stage = '';
  let strength = '';

  $: runId = $page.url.searchParams.get('run') || activeRunId();
  $: filteredRecommendations = filterRecommendations(data?.recommendations ?? [], query, target, stage, strength);
  $: filteredTargets = filterTargets(data?.targets ?? [], query, target, stage, strength);

  function filterRecommendations(
    items: Recommendation[],
    queryValue: string,
    targetValue: string,
    stageValue: string,
    strengthValue: string
  ): Recommendation[] {
    const q = queryValue.trim().toLowerCase();
    return items.filter((item) => {
      const hay = `${item.compound_a} ${item.compound_b} ${item.target} ${item.target_family} ${item.stage} ${item.chemical_class} ${item.evidence_strength}`.toLowerCase();
      if (q && !hay.includes(q)) return false;
      if (targetValue && item.target !== targetValue && item.target_family !== targetValue) return false;
      if (stageValue && item.stage !== stageValue) return false;
      if (strengthValue && item.evidence_strength !== strengthValue) return false;
      return true;
    });
  }

  function filterTargets(
    items: TargetInsight[],
    queryValue: string,
    targetValue: string,
    stageValue: string,
    strengthValue: string
  ): TargetInsight[] {
    const q = queryValue.trim().toLowerCase();
    return items.filter((item) => {
      const hay = `${item.name} ${item.family} ${item.stage} ${item.priority}`.toLowerCase();
      if (q && !hay.includes(q)) return false;
      if (targetValue && item.name !== targetValue && item.family !== targetValue) return false;
      if (stageValue && item.stage !== stageValue) return false;
      if (strengthValue && item.priority !== strengthValue) return false;
      return true;
    });
  }

  async function loadResults() {
    loading = true;
    error = '';
    try {
      data = await api.inferenceResults(runId, 80);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  onMount(loadResults);
</script>

<div class="page">
  <header class="page-header">
    <span class="eyebrow">Results</span>
    <h1>Review screening recommendations.</h1>
    <p class="lede">Start with recommended compound pairs, then inspect the enzyme targets and scenario notes behind them. Filters help narrow the review without requiring users to know internal pair names first.</p>
  </header>

  {#if error}<div class="error">{error}</div>{/if}

  <section class="panel stack">
    <div class="between">
      <div>
        <span class="kicker">Current result set</span>
        <h2>{data?.scenario?.crop || 'Selected crop'} vs {data?.scenario?.weed || 'selected weed'}</h2>
        <p class="muted small">{data?.scenario?.growth_stage ? data.scenario.growth_stage.replaceAll('_', ' ') : 'Latest available outputs'}</p>
      </div>
      <div class="row">
        <a class="secondary" href="/analyze">Run another analysis</a>
        <a class="primary" href="/reports">Generate report</a>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" class:active={view === 'pairs'} on:click={() => (view = 'pairs')}>Candidate pairs</button>
      <button class="tab" class:active={view === 'targets'} on:click={() => (view = 'targets')}>Enzyme targets</button>
      <button class="tab" class:active={view === 'scenario'} on:click={() => (view = 'scenario')}>Scenario notes</button>
      <button class="tab" class:active={view === 'synergy'} on:click={() => (view = 'synergy')}>Pairing signals</button>
    </div>

    <div class="filter-bar">
      <label class="field"><span>Search visible results</span><input class="input" bind:value={query} placeholder="target, compound, stage, class…" /></label>
      <label class="field"><span>Target / family</span><select bind:value={target}><option value="">All</option>{#each data?.filters?.targets ?? [] as option}<option>{option}</option>{/each}{#each data?.filters?.target_families ?? [] as option}<option>{option}</option>{/each}</select></label>
      <label class="field"><span>Growth stage</span><select bind:value={stage}><option value="">All</option>{#each data?.filters?.stages ?? [] as option}<option>{option}</option>{/each}</select></label>
      <label class="field"><span>Evidence</span><select bind:value={strength}><option value="">All</option>{#each data?.filters?.evidence_strength ?? [] as option}<option>{option}</option>{/each}</select></label>
      <button class="secondary" on:click={() => { query=''; target=''; stage=''; strength=''; }}>Reset</button>
    </div>
  </section>

  {#if loading}
    <section class="card section">Loading screening results…</section>
  {:else if view === 'pairs'}
    <section class="result-layout section">
      <div class="stack">
        {#each filteredRecommendations as item}
          <ResultRecommendationCard {item} />
        {:else}
          <div class="card muted">No candidate pairs matched the current filters.</div>
        {/each}
      </div>
      <aside class="stack">
        <div class="card">
          <span class="kicker">How to read this</span>
          <h3>Candidate pairs are review leads.</h3>
          <p class="muted small">Use evidence strength to triage which candidates deserve explanation, assay planning, and report inclusion. Do not treat any pair as a formulation or field-use recommendation.</p>
        </div>
        <div class="notice compact"><strong>Validation required</strong><p>Every candidate needs biochemical, crop-safety, weed-response, toxicity, and environmental testing.</p></div>
      </aside>
    </section>
  {:else if view === 'targets'}
    <section class="grid two section">
      {#each filteredTargets as item}
        <ResultTargetCard {item} />
      {:else}
        <div class="card muted">No targets matched the current filters.</div>
      {/each}
    </section>
  {:else if view === 'scenario'}
    <section class="grid two section">
      {#each data?.scenario_notes ?? [] as note}
        <article class="card"><span class="kicker">Scenario note</span><h3>{note.title}</h3><p class="muted">{note.body}</p></article>
      {/each}
    </section>
  {:else}
    <section class="grid two section">
      {#each data?.synergy_notes ?? [] as note}
        <article class="card"><span class="status-pill strong">{note.evidence_strength}</span><h3>{note.members.join(' + ')}</h3><p class="muted">{note.note}</p><p class="small muted">Target: {note.target} / {note.stage}</p></article>
      {:else}
        <div class="card muted">No pairing-signal notes were available.</div>
      {/each}
    </section>
  {/if}
</div>
