<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { api, rememberRun } from '$lib/api';
  import type { InferenceOptions } from '$lib/types';

  let options: InferenceOptions | null = null;
  let crop = 'Zea mays';
  let weed = 'Amaranthus palmeri';
  let growth_stage = 'seedling_emergence';
  let analysis_goal = 'candidate_pairs';
  let profile = 'audit';
  let advanced = false;
  let loading = false;
  let error = '';

  onMount(async () => {
    try {
      options = await api.inferenceOptions();
      crop = options.defaults.crop;
      weed = options.defaults.weed;
      growth_stage = options.defaults.growth_stage;
      analysis_goal = options.defaults.goal;
      profile = options.defaults.profile;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  });

  function applyExample(example: { crop: string; weed: string; stage: string }) {
    crop = example.crop;
    weed = example.weed;
    growth_stage = example.stage;
  }

  async function start() {
    loading = true;
    error = '';
    const scenario = { crop, weed, growth_stage };
    try {
      const response = await api.startAnalysis({ scenario, analysis_goal, profile, sabio_mode: 'cache', run_benchmark: true });
      rememberRun(response.run.run_id, scenario);
      await goto(`/run/${response.run.run_id}`);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }
</script>

<div class="page narrow">
  <header class="page-header">
    <span class="eyebrow">New analysis</span>
    <h1>Set the biological context before screening.</h1>
    <p class="lede">PESI uses the crop, weed, and growth stage to frame target and compound-pair recommendations. The defaults are examples; adjust them for the scenario you want to review.</p>
  </header>

  <div class="notice compact">
    <strong>Research-use only</strong>
    <p>This workflow ranks screening hypotheses. It does not produce field-use, formulation, dose, safety, or regulatory recommendations.</p>
  </div>

  {#if error}<div class="error section">{error}</div>{/if}

  <section class="panel section stack">
    <div>
      <span class="kicker">Scenario</span>
      <h2>What should PESI analyze?</h2>
    </div>

    <div class="grid two">
      <label class="field"><span>Crop plant</span><input class="input" bind:value={crop} placeholder="Zea mays" /></label>
      <label class="field"><span>Weed plant</span><input class="input" bind:value={weed} placeholder="Amaranthus palmeri" /></label>
      <label class="field"><span>Growth stage</span><select bind:value={growth_stage}>{#each options?.growth_stages ?? [] as stage}<option value={stage.value}>{stage.label}</option>{/each}</select></label>
      <label class="field"><span>Analysis goal</span><select bind:value={analysis_goal}>{#each options?.analysis_goals ?? [] as goal}<option value={goal.value}>{goal.label}</option>{/each}</select></label>
    </div>

    <div class="option-grid">
      {#each options?.example_scenarios ?? [] as example}
        <button class="choice" type="button" on:click={() => applyExample(example)}>
          <strong>{example.crop} vs {example.weed}</strong>
          <span>{example.stage.replaceAll('_', ' ')}</span>
        </button>
      {/each}
    </div>

    <details class="disclosure" bind:open={advanced}>
      <summary>Advanced run settings</summary>
      <div class="inside grid two">
        <label class="field"><span>Backend profile</span><select bind:value={profile}><option value="audit">Audit</option><option value="medium">Medium</option><option value="large">Large</option><option value="full">Full</option></select></label>
        <p class="muted small">Most users should keep the audit profile while using the interface. Larger profiles take longer and are best used when backend resources are ready.</p>
      </div>
    </details>

    <div class="row">
      <button class="primary" disabled={loading || !crop || !weed} on:click={start}>{loading ? 'Starting analysis…' : 'Start analysis'}</button>
      <a class="secondary" href="/results">Review latest results instead</a>
    </div>
  </section>
</div>
