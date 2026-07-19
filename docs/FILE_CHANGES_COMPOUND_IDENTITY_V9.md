# File Changes — PESI v0.7.0 Compound Identity and FoodDB Invariants

## Added

- `pesi/domain/compound_identity.py`
  - Structure-backed compound identity policy.
  - Full-InChIKey and canonical-isomeric-SMILES identity.
  - Curated-record and explicit name-fallback identities.
  - Canonical unordered compound-pair keys.

- `tests/test_compound_identity_fooddb_invariants.py`
  - Structure-backed identity and invalid-SMILES tests.
  - Partner-source leakage prevention.
  - Unmatched source suppression and shared-claim suppression.
  - Source-dataset family-conflict penalty.
  - Executive-synthesis consistency checks.

- `docs/COMPOUND_IDENTITY_FOODDB_INVARIANTS_V9.md`
- `docs/FILE_CHANGES_COMPOUND_IDENTITY_V9.md`
- `docs/VALIDATION_COMPOUND_IDENTITY_V9.json`
- `docs/data_cards/compound_identity_policy_card.md`

## Modified

- `pesi/ml/pipeline.py`
  - Adds canonical compound identities to the compound pool.
  - Deduplicates compounds by canonical identity.
  - Carries structure-backed IDs through optimization and pseudo-lab artifacts.
  - Uses canonical unordered pair keys.
  - Carries source-dataset family-conflict fields into ranking.

- `pesi/etl/fooddb_loader.py`
  - Maps and joins FoodDB records by canonical compound ID.
  - Emits sources only for uniquely matched compounds.
  - Suppresses unmatched/ambiguous occurrence records.
  - Builds pair context from independently owned source sets.
  - Uses canonical compound IDs in KG extension nodes and matched-only normalization edges.
  - Normalizes legacy FoodDB mapping/source schemas at the KG trust boundary without permitting unmatched source emission.

- `pesi/domain/enzyme_identity.py`
  - Adds source-container family validation and explicit conflict metadata.

- `pesi/domain/scientific_semantics.py`
  - Penalizes source-dataset family conflict in evidence-adjusted priority.
  - Prevents conflicted rows from satisfying high/moderate gates.

- `pesi/api/services/evidence_path_service.py`
  - Performs identity-first compound and pair lookups.
  - Suppresses unmatched sources at the API trust boundary.
  - Aligns pair source arrays by canonical identity rather than display order.

- `pesi/api/services/inference_adapter.py`
  - Carries compound identity fields through recommendation cards and report scope.
  - Uses canonical pair keys for report grouping and FoodDB lookup.

- `pesi/api/services/report_interpreter.py`
  - Groups pairs by canonical identities.
  - Enforces compound-source ownership in legacy and current artifacts.
  - Adds row-level semantic invariant validation.
  - Adds immutable scientific-priority and coverage facts.
  - Corrects executive-synthesis inconsistencies.
  - Cleans scientific-gating punctuation.

- `tests/test_identity_aware_ranking.py`
  - Updates pair-provenance expectations to canonical identity keys.

- `tests/test_report_interpreter.py`
  - Strengthens matched-compound fixtures with concrete FoodDB identities.

- `tests/test_food_evidence_api.py`
  - Makes endpoint validation artifact-independent while enforcing unmatched-source suppression invariants.

- `pesi/api/config.py`
- `pesi/__init__.py`
- `pyproject.toml`
  - Version updated to `0.7.0`.

- `README.md`
  - Adds the v0.7.0 scientific identity and invariant summary.
