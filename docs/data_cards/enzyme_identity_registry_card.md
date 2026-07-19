# Data Card: PESI Canonical Enzyme Identity Registry

## Dataset purpose

The registry provides a small, auditable normalization layer for enzyme identities encountered in the current PESI pipeline. It supports deterministic grouping, family validation, evidence-path construction, and report interpretation.

## Version

- Registry version: `2026.07.17-v1`
- Product release: `0.6.0`
- Resolution policy: exact identifier or exact curated alias; no broad substring matching

## Coverage

The registry includes current-scope herbicide targets and plant enzyme records, including EPSPS, ALS/AHAS, ACCase, PPO, HCT, caffeoyl shikimate esterase, plant GH3 acyl acid/amido synthetases, drought-associated BCAT, alpha-amylase, broad cellulase activity, and selected broad plant enzyme families. Dynamic resolution supports explicit CAZy family/subfamily labels and explicit EC identifiers.

## Sources and identifiers

Records may include EC, UniProtKB, Rhea, CAZy, or internal PESI identifiers. External identifiers are retained when supplied. The registry does not mirror or redistribute complete authoritative databases.

## Construction

Entries are curated from the identities that appear in project artifacts. Synonyms are normalized only when the relationship is explicit and scientifically defensible. Broad substring or semantic-similarity matching is excluded.

## Known limitations

- Coverage is intentionally incomplete.
- A resolved name does not establish target engagement by a candidate compound.
- Broad activities and families are not exact protein identities.
- Taxon-specific isoforms, paralogs, splice variants, and sequence-level identity require external identifiers or sequence analysis.
- Registry updates require review, tests, versioning, and provenance.

## Appropriate use

- canonical grouping and deduplication;
- report and API display normalization;
- family-conflict detection;
- strict target-atlas gating;
- reproducible benchmark counts.

## Inappropriate use

- inferring homology from names alone;
- claiming biochemical equivalence between family members;
- assigning inhibitor sensitivity without target-specific evidence;
- replacing EC, UniProtKB, Rhea, CAZy, or specialist curation.
