# PESI v0.7.0 — Compound Identity, FoodDB Ownership, and Scientific Invariants

## Scope

This release closes the remaining compound-attribution and report-consistency defects in the PESI screening pipeline. It adds a compound-identity trust boundary from compound-pool construction through FoodDB mapping, pair aggregation, evidence paths, API responses, and report synthesis.

The implementation is intentionally conservative. A source record is emitted only when PESI can prove which canonical compound identity owns it. Missing or ambiguous mappings remain unresolved rather than inheriting evidence from a same-name row or the other member of a compound pair.

## 1. Structure-backed canonical compound identity

`pesi/domain/compound_identity.py` defines the identity hierarchy:

1. Valid full InChIKey.
2. RDKit-validated canonical isomeric SMILES hash.
3. Curated source-record identifier.
4. Explicit normalized-name fallback.

A value supplied in a field named `canonical_smiles` is not trusted without parsing and canonicalization. Invalid SMILES cannot establish structure-backed identity.

Each identity exposes:

- `canonical_compound_id`
- canonical isomeric SMILES, when resolved
- full InChIKey and connectivity block, when resolved
- identity level and basis
- confidence
- whether the identity is structure-backed
- identity-policy version

Name-fallback IDs are stable record keys, not claims of chemical equivalence. Synonyms collapse only when they resolve to the same structure-backed or curated identity.

## 2. Canonical unordered pair identity

Compound pairs use an unordered key built from canonical compound IDs. Display names are retained solely for presentation.

This prevents:

- `A + B` and `B + A` duplication;
- evidence-path duplication caused by reversed display order;
- name formatting differences from creating separate pair records;
- partner-source leakage during pair-level FoodDB joins.

## 3. Compound-specific FoodDB joins

FoodDB occurrence evidence is joined through `pesi_compound_canonical_id`, not compound display name.

A compound may emit food occurrence records only when all of the following are true:

- its FoodDB mapping status is uniquely `matched`;
- a concrete FoodDB compound identifier is present;
- every returned occurrence row carries the same PESI canonical compound ID;
- the occurrence row originated from that compound’s own FoodDB mapping.

Ambiguous and unmatched mappings cannot contribute occurrence rows. Pair-level shared occurrence is calculated only after both compound-specific source sets have passed these checks.

Legacy mapping tables are normalized at the KG augmentation trust boundary. A missing historical `match_status` may be inferred as matched only when a concrete FoodDB identity is present; missing canonical ownership is reconstructed from the PESI compound record or the matched FoodDB identity. Legacy rows that cannot establish ownership are suppressed rather than attached heuristically.

## 4. Unmatched-compound source suppression

The following invariant is enforced in ETL, API evidence services, and the report interpreter:

```text
if compound_match_status != matched:
    source_count = 0
    source_names = []
    occurrence_records = []
```

If either pair member is unmatched or ambiguous:

- shared occurrence records are cleared;
- shared occurrence counts are reset to zero;
- pair semantics become `compound_unmatched`;
- the report states that no conclusion about biological absence can be drawn.

This specifically prevents the matched partner’s source list from being copied to an unmatched compound.

## 5. Row-level semantic invariant validation

`ReportInterpreter` is the final scientific trust boundary. Before synthesis, it validates every pair, compound, target, selectivity, and assay row.

The validator checks and corrects:

- unmatched compound with nonzero occurrence records;
- matched label without a concrete FoodDB identity;
- shared occurrence when either compound is unmatched;
- target-specific selectivity without paired crop-versus-weed target evidence;
- target-specific atlas mapping applied to family/process-only identity;
- high or moderate scientific priority despite unresolved/model-only compound-target evidence;
- source-dataset family conflicts that were not reflected in evidence gating.

Corrections are recorded in `semantic_validation.row_invariants`, including correction codes, affected rows, checked-row totals, and policy metadata.

## 6. Source-dataset family-conflict tracking

A source container is provenance, not proof of enzyme-family membership. PESI compares family-bearing dataset names with the canonical enzyme family.

For example, a caffeoyl shikimate esterase row found in a BAHD-labelled workbook is retained for audit but receives:

- `source_dataset_family_hint`
- `source_dataset_family_validation_status`
- `source_dataset_family_conflict`
- `source_dataset_family_reason`

A conflict reduces evidence-adjusted scientific priority and adds an explicit gating reason. Correcting the canonical family does not erase the provenance defect.

## 7. Evidence-adjusted ranking invariants

Simulation-derived response rank remains separate from scientific validation priority.

High or moderate scientific priority cannot survive the final row gate when:

- compound-target support is model-derived or unresolved;
- target identity is only family/process level;
- target-atlas mapping is not target-specific;
- source-dataset family conflict remains;
- biological evidence layers are absent or weak.

The report continues to retain the simulation output for assay-design triage while presenting the lower, evidence-adjusted scientific priority.

## 8. Executive-summary consistency

The deterministic synthesis gate now treats these as immutable facts:

- high, moderate, exploratory, and not-prioritizable context counts;
- complete, partial, and unavailable simulation-coverage counts;
- compound-specific and pair-level FoodDB states;
- target-specific versus family/process atlas counts.

The gate rejects model text that:

- equates complete simulation coverage with stronger scientific evidence;
- says all contexts are exploratory when some are not prioritizable;
- invents high or moderate scientific priorities;
- contradicts shared-occurrence counts;
- overstates food-source utility or field readiness.

## 9. Regeneration requirement

After applying this patch, regenerate the analysis run before evaluating the next full report. Existing artifacts can be interpreted conservatively, but a new run is required to populate:

- structure-backed compound IDs;
- canonical pair keys;
- compound-specific FoodDB source ownership;
- source-dataset family-conflict fields;
- corrected evidence-adjusted priority records.

## Scientific boundary

This release improves identity integrity, provenance, and ranking discipline. It does not convert computational screening into experimental evidence. Candidate pairs still require target-engagement assays, comparative crop/weed testing, toxicology, environmental assessment, formulation work, and source-extractability validation.
