# Model Card — Aim 4 Herbicide-Biology-Aware Optimizer

## Purpose
Ranks candidate plant-derived or inhibitor-like compound pairs for critical enzyme-state intervention.

## Inputs
- Aim 3 critical transition enzyme table.
- FoodDB/SKiD compound evidence.
- Herbicide target atlas rules.
- Compound suitability rules.
- Contextual crop/weed selectivity proxy.

## Outputs
- `outputs/aim4_optimized_interventions.csv`
- `outputs/aim4_inhibit_synergy_groups.csv`
- `outputs/compound_pool.csv`
- `outputs/aim4_optimization_report.json`

## Evidence classes
The optimizer produces model-inferred hypotheses, not validated pesticide recommendations.

## Known limitations
- Synergy requires wet-lab enzyme and crop/weed dose-response validation.
- Crop/weed selectivity is scenario-contextual and proxy-based.
- Compound toxicity/persistence proxies are not regulatory endpoints.
