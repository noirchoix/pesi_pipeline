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
        {#if report.interpretation_mode}
          <div class="interpretation-mode" aria-label="Report interpretation method">
            <strong>Interpretation method</strong>
            <span>{report.interpretation_mode.label}</span>
            {#if report.interpretation_mode.model}<small>{report.interpretation_mode.model}</small>{/if}
          </div>
        {/if}
      </div>
      {#each report.sections as section}
        <article class="report-section"><h3>{section.title}</h3><p>{section.body}</p></article>
      {/each}
      <div class="notice compact"><strong>Required caveats</strong><ul>{#each report.caveats as caveat}<li>{caveat}</li>{/each}</ul></div>
    </section>

    <section class="grid two section">
      <div class="stack">
        <h2>Grouped candidate pairs</h2>
        {#if report.pair_groups?.length}
          {#each report.pair_groups.slice(0, 5) as group}
            <article class="report-pair">
              <div class="between compact-row">
                <h3>{group.pair_label}</h3>
                <span class="status-chip">{group.evidence_strength}</span>
              </div>
              <p><strong>Targets:</strong> {group.targets.map((target) => target.target).join(', ')}</p>
              <p>{group.natural_source_context.interpretation}</p>
              <p><strong>Assay priority:</strong> {group.assay_prioritization.overall_priority}</p>
            </article>
          {/each}
        {:else}
          {#each report.recommendations.slice(0, 4) as item}<ResultRecommendationCard {item} />{/each}
        {/if}
      </div>
      <div class="stack">
        <h2>Included targets</h2>
        {#each report.targets.slice(0, 4) as item}<ResultTargetCard {item} />{/each}
      </div>
    </section>
  {/if}
</div>


<style>
  .interpretation-mode {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.45rem;
    margin-top: 0.75rem;
    padding: 0.45rem 0.7rem;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: var(--surface-soft, #f6faf7);
    font-size: 0.86rem;
  }

  .interpretation-mode span,
  .interpretation-mode small {
    color: var(--muted);
  }

  .report-pair {
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--surface);
    padding: 1rem;
  }

  .report-pair h3 {
    margin: 0;
  }

  .report-pair p {
    margin: 0.55rem 0 0;
  }

  .compact-row {
    gap: 0.75rem;
    align-items: flex-start;
  }

  .status-chip {
    flex: 0 0 auto;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 0.25rem 0.55rem;
    font-size: 0.78rem;
    font-weight: 750;
    color: var(--accent);
    background: var(--accent-soft);
  }
</style>
