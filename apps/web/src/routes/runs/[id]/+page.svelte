<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  onMount(() => goto(`/run/${$page.params.id}`));
</script>
<div class="page"><div class="card">Redirecting to run status…</div></div>
