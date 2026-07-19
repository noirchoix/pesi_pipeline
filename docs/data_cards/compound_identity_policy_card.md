# Data Card — PESI Compound Identity Policy

## Purpose

Provide stable compound identities for deduplication, FoodDB attribution, pair provenance, and report auditability without asserting chemical equivalence from names alone.

## Identity precedence

1. Valid full InChIKey — structure-backed, confidence 1.00.
2. RDKit-validated canonical isomeric SMILES hash — structure-backed, confidence 0.98.
3. Curated source-record identifier — record-backed, not structure-backed, confidence 0.85.
4. Normalized-name hash — fallback only, not structure-backed, confidence 0.45 or lower.

## Validation rules

- Supplied SMILES are parsed and canonicalized before use.
- Invalid SMILES cannot create a structure-backed identity.
- InChIKey format must be complete and valid.
- Name fallback IDs are not evidence that two chemical records are identical.
- FoodDB occurrence joins require a unique matched FoodDB identity.
- Pair keys are unordered combinations of canonical compound IDs.

## Known limitations

- Salt/solvate normalization is not asserted unless structures resolve to the same canonical identity.
- Tautomer standardization is not currently applied beyond RDKit canonical isomeric SMILES.
- Stereochemistry is retained when represented.
- Source-record identities may represent the same chemical across different resources until a structure-backed crosswalk is available.

## Version

`2026.07.19-v1`
