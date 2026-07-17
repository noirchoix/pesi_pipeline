# PESI-KG 0.5.0 — Food Source and Evidence Path Upgrade

## Added

- Food chemistry bundle discovery and ingestion.
- Identifier-first PESI-to-FoodDB compound normalization.
- Compound-to-food occurrence artifacts.
- Pair-level shared and individual food-source context.
- FoodDB node and relation extension in the existing SQLite KG.
- Recommendation evidence-path service.
- Enzyme-state reasoning service.
- Scenario-selectivity, synergy, compound-intelligence, proxy, and assay-prioritization interpretation.
- New inference and diagnostic API endpoints.
- Natural-source and evidence-path frontend panels.
- Food/source and evidence-confidence sections in reports.
- FoodDB mapping, idempotency, evidence-path, report, and API tests.

## Modified

- Main pipeline now performs food-source mapping after pair optimization and pseudo-lab generation.
- Loader registry recognizes `raw/food_chemistry` and legacy FoodDB layouts.
- Inference results include source-context previews and mapping coverage.
- Recommendation and target explanations receive the complete evidence payload.
- Diagnostics expose mapping tables, proxy registers, and pseudo-lab rows.
- Version increased from 0.4.0 to 0.5.0.

## Validation

```text
Python compile check: passed
pytest: 20 passed
Svelte check: 0 errors, 0 warnings
Svelte production build: passed
```

## Packaged mapping result

```text
compound-pool rows:                    400
matched compounds:                     248
compound match coverage:               0.6200
recommended unique compounds:           65
recommended compounds matched:          40
recommended match coverage:           0.6154
retained food-source rows:            4,400
pair-context rows:                      293
pairs with shared source context:        30
```

## Boundary

This upgrade adds source context and provenance. It does not convert food occurrence into an intervention, extraction, efficacy, safety, or field-use claim.
