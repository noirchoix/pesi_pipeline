<script lang="ts">
  import type { Explanation } from '$lib/types';
  export let explanation: Explanation | null = null;
</script>

{#if explanation}
  <div class="panel stack readable-output">
    <div>
      <span class="kicker">Readable rationale</span>
      <h2>{explanation.title}</h2>
      <p class="lede">{explanation.lead}</p>
      {#if explanation.ai_source}
        <span class="status-pill">{explanation.ai_source === 'deepseek' ? 'AI-generated' : 'Artifact-grounded fallback'}</span>
      {/if}
    </div>

    <div class="grid two">
      {#each explanation.sections ?? [] as section}
        <section class="explanation-section">
          <h3>{section.title}</h3>
          <p>{section.body}</p>
        </section>
      {/each}
    </div>

    <div class="notice compact">
      <strong>Research-use boundary</strong>
      <ul>
        {#each explanation.caveats ?? [] as caveat}<li>{caveat}</li>{/each}
      </ul>
    </div>
  </div>
{/if}
