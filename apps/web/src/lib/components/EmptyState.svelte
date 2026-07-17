<script lang="ts">
  export let title = 'Nothing to show yet';
  export let message = 'Run the analysis or refresh the page after results are available.';
</script>

<div class="empty">
  <strong>{title}</strong>
  <p>{message}</p>
  <slot />
</div>

<style>
  .empty { border:1px dashed var(--line-strong); border-radius:var(--radius); padding:1rem; background:var(--surface); color:var(--muted); }
  strong { display:block; color:var(--ink); margin-bottom:.25rem; }
  p { margin:0; line-height:1.55; }
</style>
