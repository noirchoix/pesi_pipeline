<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import ProgressStepper from '$components/ProgressStepper.svelte';
  import { api } from '$lib/api';
  import type { AnalysisProgress } from '$lib/types';

  export let data: { id?: string };
  let progress: AnalysisProgress | null = null;
  let logs: string[] = [];
  let error = '';
  let timer: ReturnType<typeof setInterval> | null = null;

  $: runId = data?.id ?? '';

  async function load() {
    if (!runId) return;
    try {
      progress = await api.analysisProgress(runId);
      if (progress.status === 'succeeded' || progress.status === 'failed') {
        if (timer) clearInterval(timer);
        timer = null;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function maybeLoadLogs(event: Event) {
    const node = event.currentTarget as HTMLDetailsElement;
    if (node.open) loadLogs();
  }

  async function loadLogs() {
    try {
      const response = await api.logs(runId);
      logs = response.lines ?? [];
    } catch (err) {
      logs = [err instanceof Error ? err.message : String(err)];
    }
  }

  onMount(() => {
    load();
    timer = setInterval(load, 2500);
  });
  onDestroy(() => { if (timer) clearInterval(timer); });
</script>

<div class="page narrow">
  <header class="page-header">
    <span class="eyebrow">Run analysis</span>
    <h1>{progress?.status === 'succeeded' ? 'Results are ready.' : 'Screening is in progress.'}</h1>
    <p class="lede">{progress?.message ?? 'PESI is preparing the analysis status.'}</p>
  </header>

  {#if error}<div class="error">{error}</div>{/if}

  <section class="panel stack">
    <div class="between">
      <div>
        <span class={`status-pill ${progress?.status === 'succeeded' ? 'complete' : progress?.status === 'failed' ? 'error' : 'current'}`}>{progress?.status ?? 'Loading'}</span>
        <p class="muted small section">Run ID: <span class="mono">{runId}</span></p>
      </div>
      {#if progress?.status === 'succeeded'}
        <a class="primary" href={`/results?run=${runId}`}>Open results</a>
      {/if}
    </div>

    <ProgressStepper steps={progress?.steps ?? []} />

    {#if progress?.status === 'failed'}
      <div class="error">{progress.error ?? 'The backend run failed. Open the technical log below for details.'}</div>
    {/if}
  </section>

  <details class="disclosure section" on:toggle={maybeLoadLogs}>
    <summary>Technical log for developer diagnostics</summary>
    <div class="inside"><pre class="report">{logs.join('\n') || 'Open this section to load the backend log.'}</pre></div>
  </details>
</div>
