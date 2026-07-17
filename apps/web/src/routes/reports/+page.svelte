<script lang="ts">
  import { onMount } from 'svelte';
  import ResultRecommendationCard from '$components/ResultRecommendationCard.svelte';
  import ResultTargetCard from '$components/ResultTargetCard.svelte';
  import { activeRunId, api, rememberedScenario } from '$lib/api';
  import type { ReadableReport } from '$lib/types';

  let report: ReadableReport | null = null;
  let report_type = 'summary';
  let loading = false;
  let error = '';
  let runId = '';
  let downloading = false;

  async function generate() {
    loading = true;
    error = '';
    try {
      runId = activeRunId();
      report = await api.inferenceReport({ run_id: runId || undefined, report_type, scenario: rememberedScenario() });
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  async function downloadHtml() {
    downloading = true;
    error = '';
    try {
      const blob = await api.inferenceReportHtml({ run_id: activeRunId() || undefined, report_type, scenario: rememberedScenario() });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `pesi-${report_type}-research-report.html`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      downloading = false;
    }
  }

  onMount(generate);
</script>

<div class="page">
  <header class="page-header">
    <span class="eyebrow">Report</span>
    <h1>Build a readable research report.</h1>
    <p class="lede">The report translates screening outputs into scenario, enzyme-state, pathway, candidate-pair, natural-source, evidence-confidence, and validation sections. Developer checks and raw technical tables stay out of the main report.</p>
  </header>

  {#if error}<div class="error">{error}</div>{/if}

  <section class="panel stack">
    <div class="between">
      <div>
        <span class="kicker">Report builder</span>
        <h2>Choose report depth</h2>
      </div>
      <div class="row">
        <select bind:value={report_type}><option value="summary">Summary report</option><option value="full">Full review report</option></select>
        <button class="primary" disabled={loading} on:click={generate}>{loading ? 'Generating…' : 'Generate report'}</button>
        <button class="secondary" disabled={downloading || loading} on:click={downloadHtml}>{downloading ? 'Preparing…' : 'Download HTML'}</button>
      </div>
    </div>
  </section>

  {#if report}
    <section class="panel section report-readable">
      <div>
        <span class="eyebrow">Research-use report</span>
        <h1>{report.title}</h1>
        <p class="lede">{report.intro}</p>
      </div>
      {#each report.sections as section}
        <article class="report-section"><h3>{section.title}</h3><p>{section.body}</p></article>
      {/each}
      <div class="notice compact"><strong>Required caveats</strong><ul>{#each report.caveats as caveat}<li>{caveat}</li>{/each}</ul></div>
    </section>

    <section class="grid two section">
      <div class="stack">
        <h2>Included candidate pairs</h2>
        {#each report.recommendations.slice(0, 4) as item}<ResultRecommendationCard {item} />{/each}
      </div>
      <div class="stack">
        <h2>Included targets</h2>
        {#each report.targets.slice(0, 4) as item}<ResultTargetCard {item} />{/each}
      </div>
    </section>
  {/if}
</div>
