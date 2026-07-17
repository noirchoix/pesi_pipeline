<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { TargetInsight } from '$lib/types';
  import { compactText } from '$lib/format';

  export let target: TargetInsight;
  export let expanded = false;
  const dispatch = createEventDispatcher<{ explain: TargetInsight }>();
</script>

<article class="target-card">
  <div class="head">
    <div>
      <span class="kicker">Enzyme target</span>
      <h3>{compactText(target.name, 84)}</h3>
      <p>{target.reason}</p>
    </div>
    <span class="priority">{target.priority}</span>
  </div>
  <div class="facts">
    <div><span>Enzyme class</span><strong>{target.family}</strong></div>
    <div><span>Growth context</span><strong>{target.stage}</strong></div>
  </div>
  <div class="actions">
    <button class="secondary" on:click={() => (expanded = !expanded)}>{expanded ? 'Hide notes' : 'Why review this?'}</button>
    <button class="ghost" on:click={() => dispatch('explain', target)}>Explain target</button>
  </div>
  {#if expanded}
    <div class="details">
      <strong>Biological signal</strong>
      <p>{target.biology}</p>
      <strong>Validation boundary</strong>
      <p>{target.validationNeed}</p>
    </div>
  {/if}
</article>

<style>
  .target-card { border:1px solid var(--line); border-radius:var(--radius-lg); background:var(--surface); box-shadow:var(--shadow-card); padding:1rem; min-width:0; }
  .head { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; }
  h3 { margin:.25rem 0 .25rem; font-size:1.03rem; overflow-wrap:anywhere; }
  p { margin:0; color:var(--muted); line-height:1.5; font-size:.9rem; }
  .priority { border-radius:999px; padding:.28rem .55rem; color:var(--accent-ink); background:var(--accent-soft); border:1px solid color-mix(in oklab, var(--accent) 20%, var(--line)); font-size:.74rem; font-weight:850; white-space:nowrap; }
  .facts { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.55rem; margin:.85rem 0; }
  .facts div { border:1px solid var(--line); border-radius:12px; padding:.65rem; background:#fbfcfa; min-width:0; }
  .facts span { display:block; color:var(--subtle); font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; font-weight:850; }
  .facts strong { display:block; margin-top:.25rem; font-size:.86rem; overflow-wrap:anywhere; }
  .actions { display:flex; gap:.55rem; flex-wrap:wrap; }
  .details { margin-top:.85rem; padding-top:.85rem; border-top:1px solid var(--line); }
  .details strong { display:block; margin:.45rem 0 .2rem; }
  @media (max-width:760px){ .head{flex-direction:column;} .facts{grid-template-columns:1fr;} }
</style>
