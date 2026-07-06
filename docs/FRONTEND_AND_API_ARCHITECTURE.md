# PESI-KG Frontend and API Architecture

## Design stance

The UI uses an industrial-botanical research console aesthetic: parchment grid background, high-density evidence cards, muted green accent, and explicit caveat banners. The memorable anchor is the research-led dashboard grid that resembles a lab notebook crossed with a KG operations console.

## Frontend principles

- SvelteKit file-based routing.
- TypeScript API boundary and shared domain types.
- Centralized API client with normalized errors.
- Loading/error/success states on data-heavy pages.
- Expandable intervention evidence cards instead of raw-only CSV views.
- Caveat-first presentation for computational pesticide outputs.

## Backend principles

- FastAPI application factory.
- Versioned `/api/v1` routes.
- API key authentication dependency.
- Background subprocess runner around existing CLI.
- Safe path resolution under project root.
- Artifact reader service for CSV/JSON/SQLite outputs.
- Artifact-grounded interpretation service.
- HTML/JSON report builder.

## Production deployment notes

For internal/local use, `VITE_PESI_API_KEY` can be configured in the UI environment. For public or multi-user deployments, put the UI behind a server-side session and proxy API requests server-side so the API key is never exposed to browsers.
