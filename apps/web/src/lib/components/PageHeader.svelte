<script lang="ts">
  export let eyebrow = '';
  export let title: string;
  export let description = '';
</script>

<section class="page-header">
  {#if eyebrow}<span class="eyebrow">{eyebrow}</span>{/if}
  <h1>{title}</h1>
  {#if description}<p class="lede">{description}</p>{/if}
  <slot />
</section>
