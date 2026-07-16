# Inference Product v3 Change Log

## Backend added

- `pesi/api/routes/inference.py`
- `pesi/api/services/inference_adapter.py`
- `pesi/api/services/llm_client.py`
- New inference endpoints for options, run launch, progress, consolidated results, explanations, and reports.
- Optional server-side DeepSeek client with deterministic fallback.
- New environment settings in `pesi/api/config.py`.
- New tests in `tests/test_inference_api.py`.

## Frontend added / rebuilt

- `src/routes/analyze/+page.svelte`
- `src/routes/run/[id]/+page.svelte`
- `src/routes/run/[id]/+page.ts`
- `src/routes/results/+page.svelte`
- `src/routes/explain/+page.svelte`
- `src/routes/reports/+page.svelte`
- `src/routes/diagnostics/+page.svelte`
- `src/lib/components/ProgressStepper.svelte`
- `src/lib/components/ResultRecommendationCard.svelte`
- `src/lib/components/ResultTargetCard.svelte`
- `src/lib/components/ExplanationPanel.svelte`

## Frontend modified

- `src/routes/+layout.svelte`
- `src/routes/+page.svelte`
- `src/routes/settings/+page.svelte`
- `src/lib/api.ts`
- `src/lib/types.ts`
- `src/lib/app.css`
- `src/lib/components/DataTable.svelte`

## Frontend removed as active product surface

- Backend-first recommendation/target components and client-side inference adapter were removed from active use.
- Legacy routes redirect to the new inference product flow.

## Validation

- `python -m py_compile $(find pesi/api -name '*.py')`
- `pytest -q` → `14 passed`
