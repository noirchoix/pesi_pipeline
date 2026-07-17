<script lang="ts">
  import '$lib/app.css';
  import { page } from '$app/stores';

  const nav = [
    { href: '/', label: 'Start', hint: 'What PESI does' },
    { href: '/analyze', label: 'New analysis', hint: 'Set crop, weed, stage' },
    { href: '/results', label: 'Results', hint: 'Review candidates' },
    { href: '/explain', label: 'Explain', hint: 'Readable rationale' },
    { href: '/reports', label: 'Report', hint: 'Export summary' },
    { href: '/diagnostics', label: 'Diagnostics', hint: 'Developer outputs' },
    { href: '/settings', label: 'Settings', hint: 'Connection' }
  ];

  $: current = $page.url.pathname;
  function active(href: string): boolean {
    if (href === '/') return current === '/';
    return current.startsWith(href);
  }
</script>

<div class="shell">
  <aside>
    <a class="brand" href="/" aria-label="PESI home">
      <span>PESI</span>
      <strong>Plant enzyme inference</strong>
    </a>
    <nav aria-label="Main navigation">
      {#each nav as item}
        <a class:active={active(item.href)} href={item.href}>
          <span>{item.label}</span>
          <small>{item.hint}</small>
        </a>
      {/each}
    </nav>
    <div class="sidebar-note">
      <strong>Screening support</strong>
      <span>Prioritize research candidates. Do not treat outputs as application instructions.</span>
    </div>
  </aside>
  <main><slot /></main>
</div>

<style>
  .shell { display:grid; grid-template-columns:248px minmax(0,1fr); min-height:100vh; width:100%; max-width:100vw; overflow-x:hidden; }
  aside { position:sticky; top:0; height:100vh; padding:1rem; border-right:1px solid var(--line); background:rgba(250,251,248,.94); backdrop-filter:blur(16px); display:flex; flex-direction:column; gap:1rem; }
  .brand { padding:.85rem; border:1px solid var(--line); border-radius:18px; background:var(--surface); box-shadow:var(--shadow-card); }
  .brand span { display:block; font-weight:900; letter-spacing:-.06em; font-size:1.55rem; line-height:1; }
  .brand strong { display:block; margin-top:.25rem; color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.1em; }
  nav { display:flex; flex-direction:column; gap:.22rem; }
  nav a { display:grid; gap:.15rem; padding:.67rem .75rem; border-radius:13px; color:var(--muted); border:1px solid transparent; }
  nav a span { font-weight:800; font-size:.9rem; }
  nav a small { font-size:.72rem; color:var(--subtle); }
  nav a:hover, nav a.active { color:var(--ink); background:var(--surface); border-color:var(--line); }
  nav a.active { box-shadow:var(--shadow-card); }
  .sidebar-note { margin-top:auto; padding:.85rem; border-radius:16px; background:var(--accent-soft); border:1px solid color-mix(in oklab, var(--accent) 20%, var(--line)); color:var(--accent-ink); }
  .sidebar-note strong { display:block; font-size:.86rem; }
  .sidebar-note span { display:block; margin-top:.25rem; font-size:.78rem; line-height:1.45; }
  main { min-width:0; width:100%; max-width:100%; overflow-x:hidden; }
  @media (max-width:900px){ .shell{grid-template-columns:1fr;} aside{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line);} nav{flex-direction:row;overflow-x:auto;overflow-y:hidden;padding-bottom:.25rem;max-width:100%;} nav a{min-width:9rem;flex:0 0 auto;} .sidebar-note{display:none;} }
</style>
