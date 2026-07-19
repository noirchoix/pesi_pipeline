# File Changes — Canonical Enzyme Identity and Evidence-Adjusted Ranking v0.6.0

## Added

- `pesi/domain/enzyme_identity.py`
- `data/reference/enzyme_identity_registry.csv`
- `tests/test_enzyme_identity_resolution.py`
- `tests/test_identity_aware_ranking.py`
- `docs/ENZYME_IDENTITY_AND_EVIDENCE_RANKING_V8.md`
- `docs/FILE_CHANGES_ENZYME_IDENTITY_V8.md`
- `docs/VALIDATION_ENZYME_IDENTITY_V8.json`
- `docs/data_cards/enzyme_identity_registry_card.md`

## Modified

- `pesi/domain/scientific_semantics.py`
- `pesi/domain/herbicide_targets.py`
- `pesi/domain/selectivity.py`
- `pesi/ml/pipeline.py`
- `pesi/benchmarks/evaluate.py`
- `pesi/etl/fooddb_loader.py`
- `pesi/api/services/evidence_path_service.py`
- `pesi/api/services/report_interpreter.py`
- `pesi/api/services/inference_adapter.py`
- `pesi/api/services/interpretation_service.py`
- `pesi/api/config.py`
- `pesi/__init__.py`
- `data/reference/herbicide_target_reference.csv`
- `tests/test_report_interpreter.py`
- `pyproject.toml`
- `MANIFEST.in`
- `README.md`

## Deliberately unchanged

- Frontend application files: the existing UI consumes the enriched report/API payload without a required route or dependency change.
- Raw scientific datasets.
- User `.env` and model-provider secrets.
- Historical output artifacts: existing artifacts are interpreted conservatively; new runs regenerate canonical fields and evidence-adjusted rankings.
