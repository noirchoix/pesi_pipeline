<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  onMount(() => goto('/results'));
</script>
<div class="page"><div class="card">Redirecting to /results…</div></div>
