<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { RecommendationCard } from '$lib/types';
  import { compactText } from '$lib/format';

  export let card: RecommendationCard;
  export let expanded = false;

  const dispatch = createEventDispatcher<{ explain: RecommendationCard; report: RecommendationCard }>();
</script>

<article class="recommendation">
  <div class="head">
    <div>
      <span class="kicker">Candidate pair</span>
      <h3>{compactText(card.compounds[0], 52)} + {compactText(card.compounds[1], 52)}</h3>
      <p>{card.shortReason}</p>
    </div>
    <div class="badges">
      <span class="badge strength">{card.evidenceStrength} lead</span>
      <span class="badge risk">{card.riskLevel}</span>
    </div>
  </div>

  <div class="facts">
    <div><span>Target enzyme</span><strong>{compactText(card.target, 72)}</strong></div>
    <div><span>Growth context</span><strong>{card.stage}</strong></div>
    <div><span>Target class</span><strong>{compactText(card.targetFamily, 54)}</strong></div>
    <div><span>Compound pattern</span><strong>{compactText(card.classLabel, 72)}</strong></div>
  </div>

  <div class="actions">
    <button class="secondary" on:click={() => (expanded = !expanded)}>{expanded ? 'Hide review notes' : 'Why review this?'}</button>
    <button class="secondary" on:click={() => dispatch('explain', card)}>Explain this pair</button>
    <button class="ghost" on:click={() => dispatch('report', card)}>Save for report</button>
  </div>

  {#if expanded}
    <div class="rationale">
      <div><strong>Biological fit</strong><p>{card.biologicalReason}</p></div>
      <div><strong>Chemical fit</strong><p>{card.chemicalReason}</p></div>
      <div><strong>Pairing support</strong><p>{card.synergyReason}</p></div>
      <div class="caveat"><strong>Before any use claim</strong><ul>{#each card.validationSteps as step}<li>{step}</li>{/each}</ul></div>
    </div>
  {/if}
</article>

<style>
  .recommendation { border:1px solid var(--line); border-radius:var(--radius-lg); background:var(--surface); box-shadow:var(--shadow-card); padding:1rem; min-width:0; }
  .head { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; }
  h3 { margin:.25rem 0 .25rem; font-size:1.03rem; overflow-wrap:anywhere; }
  p { margin:0; color:var(--muted); line-height:1.5; font-size:.9rem; }
  .badges { display:flex; gap:.4rem; flex-wrap:wrap; justify-content:flex-end; }
  .badge { border:1px solid var(--line); border-radius:999px; padding:.28rem .55rem; font-size:.74rem; font-weight:850; white-space:nowrap; }
  .strength { color:var(--accent-ink); background:var(--accent-soft); }
  .risk { color:#6f4b1c; background:#fff8e8; border-color:#ead6a7; }
  .facts { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.55rem; margin:.9rem 0; }
  .facts div { min-width:0; border:1px solid var(--line); border-radius:12px; padding:.65rem; background:#fbfcfa; }
  .facts span { display:block; color:var(--subtle); font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; font-weight:850; }
  .facts strong { display:block; margin-top:.25rem; font-size:.86rem; overflow-wrap:anywhere; }
  .actions { display:flex; gap:.55rem; flex-wrap:wrap; }
  .rationale { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; margin-top:.9rem; padding-top:.9rem; border-top:1px solid var(--line); }
  .rationale div { min-width:0; border:1px solid var(--line); border-radius:12px; padding:.75rem; background:#fbfcfa; }
  .rationale strong { display:block; margin-bottom:.25rem; }
  .rationale ul { margin:.35rem 0 0; padding-left:1.1rem; color:var(--muted); font-size:.9rem; line-height:1.45; }
  .caveat { background:#fff8e8 !important; border-color:#ead6a7 !important; }
  @media (max-width:860px){ .head{flex-direction:column;} .badges{justify-content:flex-start;} .facts,.rationale{grid-template-columns:1fr;} }
</style>
