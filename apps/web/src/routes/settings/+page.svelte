<script lang="ts">
  import { onMount } from 'svelte';
  import { activeRunId, api } from '$lib/api';

  let health: Record<string, unknown> | null = null;
  let error = '';
  let runId = '';

  onMount(async () => {
    runId = activeRunId();
    try { health = await api.health(); } catch (err) { error = err instanceof Error ? err.message : String(err); }
  });
</script>

<div class="page narrow">
  <header class="page-header">
    <span class="eyebrow">Settings</span>
    <h1>Connection and AI interpretation settings.</h1>
    <p class="lede">The frontend talks to SvelteKit first, then SvelteKit proxies requests to the FastAPI backend. Model keys must stay in the backend environment.</p>
  </header>

  {#if error}<div class="error">{error}</div>{/if}

  <section class="grid two">
    <div class="panel">
      <span class="kicker">Backend</span>
      <h2>API connection</h2>
      <p class="muted">Status: {health?.status ?? 'not checked'}</p>
      <p class="muted">Service: {health?.service ?? '—'}</p>
      <p class="muted">Version: {health?.version ?? '—'}</p>
      <p class="muted small">Active run: <span class="mono">{runId || 'none selected'}</span></p>
    </div>
    <div class="panel">
      <span class="kicker">AI explanation</span>
      <h2>DeepSeek stays server-side</h2>
      <p class="muted">Put <span class="mono">DEEPSEEK_API_KEY</span>, <span class="mono">PESI_AI_ENABLED=true</span>, and the model settings in the backend/root environment. Do not put model keys in Vite variables.</p>
      <pre class="report">DEEPSEEK_API_KEY=...
PESI_AI_ENABLED=true
PESI_AI_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-chat</pre>
    </div>
  </section>
</div>
