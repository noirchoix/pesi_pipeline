<script lang="ts">
  import { compactText, formatNumber } from '$lib/format';
  import type { Aim4Row } from '$lib/types';
  export let row: Aim4Row;
  let open = false;
  $: score = formatNumber(row.optimization_objective);
</script>

<article class="intervention">
  <button class="summary" on:click={() => (open = !open)} aria-expanded={open}>
    <span class="main">
      <strong>{compactText(row.target_enzyme, 78)}</strong>
      <em>{row.target_family ?? 'Target family not listed'} · {row.stage ?? 'stage not listed'}</em>
    </span>
    <span class="pair">
      {compactText(row.compound_a, 34)} <b>+</b> {compactText(row.compound_b, 34)}
    </span>
    <span class="score">{score}</span>
  </button>

  {#if open}
    <div class="details">
      <div class="explain-grid">
        <div>
          <span>Why this target</span>
          <p>{row.known_inhibitor_classes ? `Known inhibitor classes: ${row.known_inhibitor_classes}` : 'Selected from enzyme-state, target-family, and growth-stage evidence.'}</p>
        </div>
        <div>
          <span>Why this pair</span>
          <p>{row.phytochemical_class_pair ? `Chemical class pairing: ${row.phytochemical_class_pair}` : 'Selected for pair score, quality filters, and portfolio diversity.'}</p>
        </div>
        <div>
          <span>Synergy signal</span>
          <p>{row.synergy_match_schema ? `${row.synergy_match_schema}; score ${formatNumber(row.synergy_group_score)}` : 'No synergy explanation returned for this row.'}</p>
        </div>
        <div>
          <span>Selectivity note</span>
          <p>Margin {formatNumber(row.scenario_selectivity_margin)} · estimated crop impact {formatNumber(row.crop_impact_estimate)}.</p>
        </div>
      </div>
      <div class="caveat">Computational candidate only. Requires toxicity, environmental, crop-safety, and wet-lab validation.</div>
    </div>
  {/if}
</article>

<style>
  .intervention { border:1px solid var(--line); background:var(--surface); border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow-card); }
  .summary { width:100%; min-width:0; display:grid; grid-template-columns: minmax(0,1.2fr) minmax(0,1fr) auto; gap:.9rem; align-items:center; padding:.9rem; background:transparent; border:0; text-align:left; color:var(--ink); }
  .summary:hover { background:var(--surface-soft); }
  .main, .pair { min-width:0; overflow-wrap:anywhere; }
  .main strong { display:block; font-size:.96rem; line-height:1.25; overflow-wrap:anywhere; }
  .main em { display:block; margin-top:.25rem; color:var(--muted); font-style:normal; font-size:.82rem; }
  .pair { color:var(--muted); line-height:1.4; font-size:.88rem; }
  .pair b { color:var(--accent); }
  .score { justify-self:end; background:var(--accent-soft); color:var(--accent-ink); border-radius:999px; padding:.35rem .55rem; font-weight:850; font-size:.82rem; }
  .details { padding:.9rem; border-top:1px solid var(--line); background:#fbfcfa; }
  .explain-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.75rem; }
  .explain-grid div { min-width:0; border:1px solid var(--line); border-radius:12px; padding:.75rem; background:var(--surface); }
  span { color:var(--subtle); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; font-weight:850; }
  p { margin:.25rem 0 0; color:var(--muted); line-height:1.5; font-size:.88rem; overflow-wrap:anywhere; }
  .caveat { margin-top:.75rem; border-left:4px solid #dfc79a; padding:.65rem .75rem; background:#fff8e8; color:#6f4b1c; border-radius:.6rem; font-size:.86rem; }
  @media (max-width: 760px) { .summary, .explain-grid { grid-template-columns:1fr; } .score { justify-self:start; } }
</style>
