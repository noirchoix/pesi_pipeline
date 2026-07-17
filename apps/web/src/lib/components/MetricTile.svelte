<script lang="ts">
  export let label: string;
  export let value: string | number | undefined | null;
  export let detail: string | undefined = undefined;
</script>

<div class="tile">
  <p>{label}</p>
  <strong>{value ?? '—'}</strong>
  {#if detail}<span>{detail}</span>{/if}
</div>

<style>
  .tile { min-height: 6.5rem; padding: .9rem; border: 1px solid var(--line); background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow-card); }
  p { margin: 0; color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 850; }
  strong { display:block; margin-top:.45rem; font-size: clamp(1.35rem, 2.4vw, 2rem); line-height: 1; letter-spacing: -.04em; }
  span { display:block; margin-top:.45rem; color: var(--muted); font-size:.84rem; line-height:1.4; }
</style>
