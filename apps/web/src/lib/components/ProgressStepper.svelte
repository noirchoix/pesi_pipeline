<script lang="ts">
  import type { ProgressStep } from '$lib/types';
  export let steps: ProgressStep[] = [];
</script>

<div class="progress-list" aria-label="Analysis progress">
  {#each steps as step, index}
    <article class={`progress-step ${step.state}`}>
      <div class="dot">{step.state === 'complete' ? '✓' : index + 1}</div>
      <div>
        <strong>{step.label}</strong>
        <span>{step.description}</span>
      </div>
    </article>
  {/each}
</div>
