<script lang="ts">
  import { page } from '$app/stores';
</script>

<div class="page">
  <section class="hero-panel">
    <span class="eyebrow">Application error</span>
    <h1>{$page.status}</h1>
    <p class="lede">{$page.error?.message ?? 'The research console could not render this route.'}</p>
    <a class="primary" href="/">Return to dashboard</a>
  </section>
</div>
