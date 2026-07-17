# PESI-KG API Contract

Base path: `/api/v1`

## Authentication

When `PESI_AUTH_MODE=required`, provide either:

```text
X-API-Key: <PESI_API_KEY>
Authorization: Bearer <PESI_API_KEY>
```

The SvelteKit app normally sends requests through its same-origin `/api/pesi/*` server proxy.

## Run lifecycle

```text
POST /runs
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/logs
GET  /runs/{run_id}/artifacts
```

Run statuses:

```text
queued → running → succeeded | failed
```

## User-facing inference contract

```text
GET    /inference/options
POST   /inference/analyses
GET    /inference/analyses/{run_id}/progress
GET    /inference/results
POST   /inference/explain/recommendation
POST   /inference/explain/target
POST   /inference/reports
```

`GET /inference/results` returns user-facing recommendation and target cards, scenario notes, source-context previews, filters, and capability metadata. Raw backend rows are intentionally not the primary response model.

## Evidence and source-context contract

```text
GET /inference/recommendations/{recommendation_id}/evidence-path
GET /inference/targets/{target_id}/state-reasoning
GET /inference/food-sources/compound?compound=<name>&limit=<n>
GET /inference/food-sources/pair?compound_a=<name>&compound_b=<name>
```

Recommendation evidence includes:

- Ordered evidence path.
- Enzyme-state reasoning.
- Scenario-selectivity interpretation.
- Pairing/synergy reasoning.
- Compound intelligence.
- Natural-source context.
- Assay-prioritization simulation.
- Direct evidence, model inference, proxy assumptions, and weak assumptions.
- Mandatory scientific caveats.

## Diagnostics/raw artifacts

```text
GET /results/kg-summary
GET /results/aim2-signatures
GET /results/aim3
GET /results/aim4
GET /results/synergy
GET /results/scenario-selectivity
GET /results/compound-pool
GET /results/food-source-report
GET /results/fooddb-matches
GET /results/food-sources
GET /results/pair-food-context
GET /results/pair-food-evidence
GET /results/proxy-evidence
GET /results/pseudo-lab
```

Tabular responses are paginated and support `limit`, `offset`, and route-specific filters.

## Report contract

`POST /inference/reports` accepts:

```json
{
  "run_id": null,
  "report_type": "summary",
  "format": "json",
  "scenario": {}
}
```

Set `format` to `html` for an exportable HTML response. Reports include source context and evidence confidence when those artifacts are available.

## Scientific boundary

All food-source, selectivity, synergy, hazard, persistence, and assay-prioritization outputs are contextual or computational evidence. They are not efficacy, safety, dosage, extraction, formulation, or field-use claims.
