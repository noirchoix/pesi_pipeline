# PESI-KG Data Card

## Scope

PESI-KG integrates plant pathway, protein, kinetic, enzyme-family, herbicide-target, compound, food-occurrence, and generated inference artifacts. Data sources differ in identifiers, taxonomic coverage, evidence depth, and measurement quality; provenance and evidence class are retained wherever the source supports them.

## Main data categories

- PlantCyc and PlantMet-style pathway/reaction context.
- BKMS, UniProt/Rhea, CAZy, SKiD, SABIO, curated enzyme-family resources.
- Herbicide target and site-of-action reference rules.
- Compound structures, descriptors, natural-product signals, and screening rules.
- Generated enzyme-state, target-ranking, pair-optimization, selectivity, synergy, proxy, and pseudo-lab artifacts.
- FoodDB-derived food chemistry data under `raw/food_chemistry`.

## Food chemistry bundle

The supplied bundle contains a DuckDB staging database and curated Parquet tables. Relevant curated coverage includes approximately:

- 61,224 compound descriptor records.
- 4,662,138 food–compound edges.
- 105,089 compound–enzyme edges.
- 1,604 compound–pathway edges.
- Food lookup records for approximately 992 foods.

The mapping layer uses exact identifiers only:

1. Exact InChIKey.
2. Unique InChIKey connectivity block.
3. Exact normalized FoodDB primary name.
4. Exact normalized FoodDB synonym.

It does not use unconstrained fuzzy matching to create food-source claims.

## Packaged mapping coverage

The current medium output artifacts contain:

- 400 compound-pool mapping records.
- 248 matched compounds, or 62.0% overall coverage.
- 65 unique compounds used in recommendations.
- 40 recommended compounds matched, or 61.54% coverage.
- 4,400 retained compound–food source rows.
- 293 pair source-context rows.
- 30 pairs with at least one shared source record.

Unmatched compounds remain explicit. Ambiguous compound mappings are retained with reduced confidence and an evidence-class suffix.

## Generated food-source artifacts

```text
compound_fooddb_matches.csv
compound_food_sources.csv
pair_food_source_context.csv
pair_food_source_evidence.csv
food_source_mapping_report.json
```

The KG extension adds `FoodDBCompound` and `FoodSource` node types and the relations `normalized_to_fooddb_compound` and `reported_in_food`.

## Provenance and evidence semantics

Food occurrence is represented as either:

- `quantified_occurrence`, when positive content values are present; or
- `reported_occurrence`, when the source reports occurrence without a usable positive content measurement.

Source confidence combines occurrence evidence, citation type, compound-match confidence, and an ambiguity penalty. It is not a safety or efficacy score.

## Sensitive data and secrets

No API keys should be committed. DeepSeek, Plant.id, and PESI application keys must be supplied through backend environment variables.

## Limitations

- Food/source occurrence does not establish extractability, useful concentration, dose, efficacy, crop safety, or field suitability.
- Missing or unmatched compounds are not evidence of absence from foods.
- FoodDB records can contain naming, synonym, ionization-state, stereochemistry, and citation inconsistencies.
- Several upstream plant/kinetic resources are incomplete or unevenly distributed across species and enzyme families.
- Generated scores and trajectories are computational inference, not experimental measurements.
