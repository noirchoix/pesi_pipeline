<script lang="ts">
  import StatusBadge from './StatusBadge.svelte';
  import { formatNumber, titleCase } from '$lib/format';
  import type { Gate } from '$lib/types';
  export let gate: Gate;
</script>

<article class="gate" class:failed={!gate.passed}>
  <div class="topline">
    <h3>{titleCase(gate.gate)}</h3>
    <StatusBadge status={gate.passed} />
  </div>
  <p>{gate.rationale}</p>
  <div class="metric">
    <span>{titleCase(gate.metric)}</span>
    <strong>{formatNumber(gate.value)}</strong>
    <em>Required: {gate.operator} {formatNumber(gate.threshold)}</em>
  </div>
</article>

<style>
  .gate { border: 1px solid var(--line); border-radius: var(--radius); padding: .9rem; background: var(--surface); box-shadow: var(--shadow-card); }
  .gate.failed { border-color: color-mix(in oklab, var(--bad) 45%, var(--line)); }
  .topline { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; }
  h3 { margin:0; font-size:.96rem; line-height:1.2; }
  p { margin:.55rem 0 .8rem; color:var(--muted); font-size:.88rem; line-height:1.48; }
  .metric { display:grid; grid-template-columns: 1fr auto; gap:.35rem .8rem; align-items:end; padding-top:.75rem; border-top:1px solid var(--line); }
  .metric span { color:var(--muted); font-size:.78rem; }
  .metric strong { font-size:1.35rem; letter-spacing:-.035em; }
  .metric em { grid-column:1 / -1; color:var(--subtle); font-style:normal; font-size:.78rem; }
</style>
