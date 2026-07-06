# PESI-KG Model Card

## Model family

PESI-KG is a multi-stage computational research pipeline rather than a single model. It combines typed KG assembly, feature engineering, weak-label/scoring models, random forest criticality modeling, enzyme-SMI interaction modeling, rule-based compound classification, and diversity-constrained portfolio selection.

## Intended use

Generate computational hypotheses for plant enzyme-state intervention research, including critical transition enzyme candidates, chemically plausible intervention pairs, and typed inhibit-synergy groups.

## Not intended use

Do not use outputs as field-use recommendations, formulation instructions, dosing guidance, or claims of herbicidal efficacy. All intervention outputs require wet-lab, crop-safety, environmental, toxicity, and regulatory validation.

## Inputs

- PlantCyc/PlantMet-style pathway and plant context data.
- BKMS, UniProt/Rhea, CAZy, SKiD, SABIO cache, curated enzyme-family workbooks.
- Herbicide target reference table.
- Compound evidence tables and generated compound descriptors.
- Optional crop/weed scenario definitions.

## Outputs

- Enzyme-state signatures.
- Critical transition enzyme rankings.
- Aim 4 optimized intervention portfolio.
- Typed inhibit-synergy groups.
- Scenario selectivity records.
- Production benchmark gate summary.
- Artifact-grounded interpretations and reports.

## Validation status

Current audit and medium runs pass 7/7 production gates. The strongest strict target benchmark is high-confidence known-target enrichment at top 50, which compares top-ranked critical enzymes against a low base-rate strict target label.

## Limitations

- Computational hypotheses only.
- Compound classes include rule-based approximations.
- Synergy groups are model-inference records, not measured synergy.
- Selectivity margin is scenario/proxy-based, not crop-safety validation.
- Data coverage and source bias can affect ranking.

## Monitoring

Track production gates, control-compound rate, target-family entropy, stage entropy, unique target count, unique compound count, max compound share, and strict known-target enrichment after every run.
