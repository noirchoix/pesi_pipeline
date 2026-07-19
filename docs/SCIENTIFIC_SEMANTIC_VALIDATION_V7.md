# PESI scientific semantic validation layer (v0.5.2)

This patch adds a conservative semantic validation layer between PESI artifacts and user-facing scientific interpretation.

## Scientific invariants

1. **Selectivity arithmetic is explicit.**
   - `scenario_selectivity_margin` now means `weed_vulnerability - crop_vulnerability` and ranges from -1 to +1.
   - `scenario_selectivity_index` is the historical centered ranking index `clip(difference + 0.5, 0, 1)`.
   - Legacy artifacts that stored the centered index in the margin field are detected and translated without corrupting old runs.

2. **Target-atlas annotations require validated identity.**
   - Exact target identity or a curated target-specific alias is required.
   - Growth stage and broad pathway words cannot create a target mapping.
   - Unvalidated targets receive no inhibitor-class or WSSA/site-of-action claim.
   - Legacy atlas columns are retained under `legacy_*` fields for audit when new runs recompute strict mappings.

3. **Evidence tiers are conservative.**
   - Direct database occurrence evidence
   - Curated reference evidence
   - User-provided scenario context
   - Model-derived inference
   - Proxy estimate
   - Unresolved or unsupported evidence

   Model-derived crop/weed assignment is no longer presented as direct biological evidence.

4. **FoodDB status is normalized.**
   - Matched, ambiguous, unmatched, or unavailable are rendered consistently.
   - An unmatched row can never appear as `ok`.
   - Food occurrence remains contextual and does not imply source usability.

5. **AI synthesis is deterministically validated.**
   - Canonical counts and coverage facts are calculated in code.
   - DeepSeek cannot replace canonical key findings.
   - Contradictory or ambiguous universal claims about shared sources, assay coverage, field readiness, efficacy, or safety trigger deterministic correction.
   - Numeric zero is preserved as a valid selectivity value rather than being treated as missing during artifact fallback.
   - The report discloses whether semantic validation passed or corrected the model output.

6. **Assay bands are explicitly dimensionless.**
   - Bands are labeled as dimensionless normalized model-input units.
   - They are not concentrations, doses, formulations, or field rates.

## Research boundary

The layer improves semantic correctness and prevents unsupported interpretation. It does not convert computational screening into experimental validation. Enzyme assays, crop/weed comparative tests, toxicity review, environmental assessment, and source-extractability work remain mandatory.
