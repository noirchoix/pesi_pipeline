<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  onMount(() => goto('/reports', { replaceState: true }));
</script>

<div class="page narrow">
  <section class="panel">
    <span class="kicker">Moved</span>
    <h1>Reports</h1>
    <p class="lede">This view is now part of the inference workflow.</p>
    <a class="primary" href="/reports">Continue</a>
  </section>
</div>
