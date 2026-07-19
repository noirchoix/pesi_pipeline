# Canonical Enzyme Identity and Evidence-Adjusted Ranking — v0.6.0

## Scope

This release adds a conservative semantic layer between heterogeneous enzyme artifacts and all downstream ranking, evidence-path, API, and report outputs. Its purpose is to prevent free-text enzyme labels, broad family names, scenario-level proxy values, and simulated response scores from being presented as stronger biological claims than the underlying evidence supports.

The implementation is deliberately scope-bounded. It provides an auditable registry for identities that occur in the current PESI data products and supports exact external identifiers when present. It does **not** claim to replace authoritative resources such as EC, UniProtKB, Rhea, or CAZy. Unknown or ambiguous identities remain unresolved rather than being assigned through broad substring similarity.

## Canonical identity resolution

`pesi/domain/enzyme_identity.py` resolves each target to a stable canonical identity using the following precedence:

1. Explicit curated external identifier, including EC, UniProtKB, Rhea, or CAZy identifiers.
2. Exact canonical name.
3. Exact curated synonym.
4. Explicit dynamic CAZy family or subfamily identifier.
5. Explicit EC identifier.
6. Stable unresolved PESI identifier.

Partial substring matching is prohibited. Identifier/name conflicts and family conflicts are retained as warnings. The original reported name and family are always preserved for audit.

The current registry explicitly distinguishes:

- exact enzyme or herbicide-target identities;
- enzyme families and CAZy subfamilies;
- broad functional activities such as cellulase activity;
- unresolved identities.

## Family ontology validation

Reported families are validated against the canonical identity. The validator can:

- accept an exact or curated family alias;
- refine a broad CAZy class to an identifier-specific family or subfamily;
- retain a compatible broad label without upgrading it to exact identity;
- correct a conflicting family while preserving the reported value;
- leave unresolved families unresolved.

Examples addressed by this release include:

- caffeoyl shikimate esterase is not grouped as a BAHD acyltransferase;
- plant GH3 acyl acid/amido synthetases are not grouped as BAHD enzymes or CAZy GH3 hydrolases;
- cellulase remains a broad functional activity unless a specific CAZy family, subfamily, sequence, or identifier is available;
- CAZy family and subfamily labels remain stable across repeated API and report passes.

## Synonym and duplicate-target consolidation

Target records are deduplicated by:

```text
canonical target identity + biological stage/context
```

Reported aliases and source records remain attached as provenance. This prevents spelling variants, punctuation variants, and known synonyms from inflating unique-target counts or portfolio-diversity metrics.

Compound pairs are canonicalized as unordered identifiers:

```text
sorted(canonical compound A, canonical compound B)
```

The same key is used by optimization, FoodDB source aggregation, evidence paths, API lookups, and report grouping. Reversed pair order cannot create a second scientific record.

## Selectivity scope

Selectivity output now declares one of two scopes:

- `scenario_level`: a crop/weed scenario baseline applied to target contexts;
- `target_specific`: permitted only when paired crop-versus-weed target evidence is available.

Target-specific scope requires target-dependent evidence such as paired expression, abundance, sequence, binding, sensitivity, or kinetic inputs. Current generic crop/weed vulnerability scores remain scenario-level and are not described as target-specific measurements.

The report continues to separate:

```text
selectivity difference = weed vulnerability - crop vulnerability
centered selectivity index = clip(selectivity difference + 0.5, 0, 1)
```

The centered index is a ranking transform, not a biological margin.

## Evidence-adjusted assay priority

Simulation-derived response rank and scientific validation priority are now separate fields.

A high simulated inhibition score cannot independently create a high scientific priority. Scientific priority is gated by:

- identity resolution level;
- strict target-atlas validation;
- direct or curated compound-target evidence;
- kinetic, structural, and plant-context support;
- simulation availability and completeness.

Current priority classes are:

- High scientific validation priority;
- Moderate scientific validation priority;
- Exploratory scientific validation priority;
- Not scientifically prioritizable from current evidence.

Each output includes explicit supporting factors and gating reasons. Simulation bands remain dimensionless model inputs and are never presented as concentrations, doses, formulations, or field rates.

## FoodDB zero-result semantics

FoodDB states are separated into:

- direct shared occurrence;
- database query completed with no shared occurrence;
- one or both compounds unmatched;
- database unavailable.

A zero-result query is not described as proof of biological absence. API query success is separately represented from scientific match status:

```text
status: ok
match_status: matched | ambiguous | unmatched
```

Reports consume `match_status` and therefore cannot render contradictory language such as `status: ok; match: unmatched`.

## Target-atlas policy

Target-specific pathway and inhibitor-class annotations require exact canonical target identity or an explicitly curated target synonym/family mapping. Broad functional activities and CAZy families may receive family/process context only. They do not inherit target-specific inhibitor classes.

## Audit fields

Identity and ranking outputs include, where applicable:

- canonical ID, name, family, and resolution level;
- registry version and resolution policy;
- reported name and family;
- family validation status and reason;
- external identifiers;
- canonical pair key and label;
- selectivity scope and scope reason;
- simulation-derived response rank;
- evidence-adjusted scientific priority;
- gating reasons and supporting factors;
- FoodDB query and match semantics.

## Research boundary

These outputs remain computational screening hypotheses. Canonicalization improves semantic correctness and auditability; it does not establish enzyme inhibition, crop safety, weed control, toxicity, environmental behavior, formulation suitability, or field efficacy. Experimental validation remains mandatory.
