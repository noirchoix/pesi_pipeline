<script lang="ts">
  import { plainStatus } from '$lib/format';
  export let status: string | boolean | undefined = undefined;
  $: raw = typeof status === 'boolean' ? (status ? 'passed' : 'failed') : (status ?? 'unknown');
  $: label = plainStatus(raw);
  $: tone = raw === 'passed' || raw === 'succeeded' || raw === 'ok' ? 'good' : raw === 'running' || raw === 'queued' ? 'warn' : 'bad';
</script>

<span class={`status ${tone}`}>{label}</span>

<style>
  .status { display:inline-flex; align-items:center; gap:.4rem; border-radius:999px; padding:.24rem .58rem; border:1px solid var(--line-strong); font-size:.7rem; font-weight:850; letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; }
  .status::before { content:''; width:.42rem; height:.42rem; border-radius:999px; background:currentColor; }
  .good { color: var(--good); background: color-mix(in oklab, var(--good) 8%, white); }
  .warn { color: var(--warn); background: color-mix(in oklab, var(--warn) 10%, white); }
  .bad { color: var(--bad); background: color-mix(in oklab, var(--bad) 8%, white); }
</style>
