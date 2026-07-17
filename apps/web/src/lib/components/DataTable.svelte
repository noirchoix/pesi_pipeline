<script lang="ts">
  import { compactText, formatNumber, labelFor } from '$lib/format';
  export let rows: Record<string, unknown>[] = [];
  export let columns: string[] = [];
  export let numericColumns: string[] = [];
  export let max = 10;
  export let empty = 'No rows available.';
  $: visible = rows.slice(0, max);
  $: shownColumns = columns.length ? columns : Object.keys(rows[0] ?? {}).slice(0, 8);
  function cell(value: unknown, column: string): string {
    return numericColumns.includes(column) ? formatNumber(value) : compactText(value, 120);
  }
</script>

{#if visible.length === 0}
  <div class="empty-table">{empty}</div>
{:else}
  <div class="table-wrap">
    <table>
      <thead>
        <tr>{#each shownColumns as column}<th>{labelFor(column)}</th>{/each}</tr>
      </thead>
      <tbody>
        {#each visible as row}
          <tr>{#each shownColumns as column}<td>{cell(row[column], column)}</td>{/each}</tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .table-wrap { width:100%; max-width:100%; min-width:0; overflow-x:auto; overflow-y:hidden; border:1px solid var(--line); border-radius: var(--radius); background: var(--surface); -webkit-overflow-scrolling: touch; }
  table { width:100%; border-collapse:collapse; min-width: 680px; }
  th, td { text-align:left; padding:.68rem .75rem; border-bottom:1px solid var(--line); vertical-align:top; }
  th { position:sticky; top:0; background:var(--surface-soft); color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; }
  td { font-size:.88rem; line-height:1.45; }
  tr:last-child td { border-bottom:none; }
  .empty-table { border:1px dashed var(--line-strong); border-radius:var(--radius); padding:1rem; color:var(--muted); background:var(--surface); }
</style>
