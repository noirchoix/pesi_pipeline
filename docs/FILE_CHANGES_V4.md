# File Changes — PESI-KG 0.5.0

This inventory is relative to the uploaded inference-product v3 baseline.

## Added backend files

```text
pesi/etl/fooddb_loader.py
pesi/api/services/evidence_path_service.py
```

## Added frontend files

```text
apps/web/src/lib/components/NaturalSourceContext.svelte
apps/web/src/lib/components/EvidencePathPanel.svelte
apps/web/src/lib/components/TargetStateReasoningPanel.svelte
```

## Added tests

```text
tests/test_fooddb_mapping.py
tests/test_evidence_path.py
tests/test_food_evidence_api.py
```

The pre-existing `tests/test_inference_api.py` was retained.

## Added documentation

```text
docs/FOOD_SOURCE_MAPPING.md
docs/EVIDENCE_PATHS.md
docs/CHANGELOG_FOOD_EVIDENCE_V4.md
docs/FILE_CHANGES_V4.md
```

## Modified backend files

```text
pesi/etl/loaders.py
pesi/ml/pipeline.py
pesi/cli/main.py
pesi/api/config.py
pesi/api/routes/inference.py
pesi/api/routes/results.py
pesi/api/services/artifact_reader.py
pesi/api/services/inference_adapter.py
```

## Modified frontend files

```text
apps/web/src/lib/api.ts
apps/web/src/lib/types.ts
apps/web/src/lib/components/ResultRecommendationCard.svelte
apps/web/src/lib/components/ResultTargetCard.svelte
apps/web/src/routes/reports/+page.svelte
apps/web/src/routes/diagnostics/+page.svelte
```

## Added deployment files

```text
.dockerignore
apps/web/.dockerignore
```

## Modified packaging/configuration files

```text
.env.example
.gitignore
docker-compose.yml
pyproject.toml
apps/web/.env.example
apps/web/Dockerfile
apps/web/package.json
apps/web/package-lock.json
README.md
DATA_CARD.md
MODEL_CARD.md
BENCHMARK_CARD.md
docs/API_CONTRACT.md
```

## Added generated output artifacts

```text
outputs_medium/compound_fooddb_matches.csv
outputs_medium/compound_food_sources.csv
outputs_medium/pair_food_source_context.csv
outputs_medium/pair_food_source_evidence.csv
outputs_medium/food_source_mapping_report.json
```

## Updated generated artifacts

```text
outputs_medium/aim1_kg_report.json
artifacts_medium/pesi_kg.sqlite
```

## Added raw data directory

```text
raw/food_chemistry/
```
