<script lang="ts">
  import { onMount } from 'svelte';
  import DataTable from '$components/DataTable.svelte';
  import { activeRunId, api } from '$lib/api';
  import type { TableResponse } from '$lib/types';

  let runs: Record<string, unknown>[] = [];
  let gates: Record<string, unknown>[] = [];
  let aim3: TableResponse | null = null;
  let aim4: TableResponse | null = null;
  let foodMatches: TableResponse | null = null;
  let pairSources: TableResponse | null = null;
  let proxyEvidence: TableResponse | null = null;
  let pseudoLab: TableResponse | null = null;
  let foodReport: Record<string, unknown> = {};
  let logs: string[] = [];
  let error = '';

  async function load() {
    try {
      const [runResp, gateResp, a3, a4, matches, pairs, proxies, pseudo, mappingReport] = await Promise.all([
        api.runs().catch(() => ({ runs: [] })),
        api.benchmarkGates().catch(() => ({ gates: [] })),
        api.aim3({ limit: 25 }),
        api.aim4({ limit: 25 }),
        api.fooddbMatches({ limit: 25 }).catch(() => null),
        api.pairFoodContextTable({ limit: 25 }).catch(() => null),
        api.proxyEvidence({ limit: 25 }).catch(() => null),
        api.pseudoLab({ limit: 25 }).catch(() => null),
        api.foodSourceReport().catch(() => ({}))
      ]);
      runs = runResp.runs ?? [];
      gates = gateResp.gates ?? [];
      aim3 = a3;
      aim4 = a4;
      foodMatches = matches;
      pairSources = pairs;
      proxyEvidence = proxies;
      pseudoLab = pseudo;
      foodReport = mappingReport;
      const id = activeRunId();
      if (id) logs = (await api.logs(id)).lines ?? [];
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }
  onMount(load);
</script>

<div class="page">
  <header class="page-header">
    <span class="eyebrow">Developer diagnostics</span>
    <h1>Backend outputs and technical checks.</h1>
    <p class="lede">This section is intentionally separated from the product workflow. It exposes run records, raw evidence tables, FoodDB mapping coverage, proxy assumptions, simulations, and logs for development and audit.</p>
  </header>

  {#if error}<div class="error">{error}</div>{/if}

  <section class="grid two">
    <div class="panel"><h2>Recent runs</h2><DataTable rows={runs} /></div>
    <div class="panel"><h2>Quality checks</h2><DataTable rows={gates} /></div>
  </section>

  <section class="grid two section">
    <div class="panel"><h2>FoodDB mapping report</h2><DataTable rows={[foodReport]} /></div>
    <div class="panel"><h2>Compound → FoodDB matches</h2><DataTable rows={foodMatches?.rows ?? []} /></div>
  </section>

  <section class="grid two section">
    <div class="panel"><h2>Pair-level food source context</h2><DataTable rows={pairSources?.rows ?? []} /></div>
    <div class="panel"><h2>Proxy evidence register</h2><DataTable rows={proxyEvidence?.rows ?? []} /></div>
  </section>

  <section class="grid two section">
    <div class="panel"><h2>Assay-prioritization simulation sample</h2><DataTable rows={pseudoLab?.rows ?? []} /></div>
    <div class="panel"><h2>Raw target table sample</h2><DataTable rows={aim3?.rows ?? []} /></div>
  </section>

  <details class="disclosure section">
    <summary>Raw candidate-pair table sample</summary>
    <div class="inside"><DataTable rows={aim4?.rows ?? []} /></div>
  </details>
  <details class="disclosure section">
    <summary>Active run technical log</summary>
    <div class="inside"><pre class="report">{logs.join('\n') || 'No active run log loaded.'}</pre></div>
  </details>
</div>
