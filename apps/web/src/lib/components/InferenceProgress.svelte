<script lang="ts">
  export let active = 0;
  const steps = [
    'Set crop and weed context',
    'Find enzyme targets',
    'Screen compound pairs',
    'Explain recommendations'
  ];
</script>

<ol class="progress" aria-label="Inference workflow">
  {#each steps as step, index}
    <li class:done={index < active} class:active={index === active}>{step}</li>
  {/each}
</ol>

<style>
  .progress { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.5rem; padding:0; margin:0; list-style:none; }
  li { border:1px solid var(--line); border-radius:999px; padding:.5rem .7rem; color:var(--muted); background:var(--surface); font-size:.82rem; font-weight:780; text-align:center; }
  li.active, li.done { color:var(--accent-ink); background:var(--accent-soft); border-color:color-mix(in oklab, var(--accent) 25%, var(--line)); }
  @media (max-width:760px){ .progress{grid-template-columns:1fr;} li{text-align:left;} }
</style>
