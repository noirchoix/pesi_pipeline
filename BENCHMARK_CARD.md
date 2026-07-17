# PESI-KG Benchmark Card

## Purpose

PESI benchmarks detect structural and scientific failure modes in the computational portfolio. They do not validate biological efficacy.

## Existing production gate families

1. Strict known-target enrichment above baseline.
2. Exclusion of solvent/reactive/generic control candidates.
3. Target-family diversity.
4. Developmental-stage diversity.
5. Individual compound concentration cap.
6. Compound portfolio breadth.
7. Target portfolio breadth.

Audit and medium baseline runs passed all seven gates. These metrics remain available under developer diagnostics rather than the primary user workflow.

## Food-source and evidence-path monitoring

Version 0.5.0 adds monitoring metrics that are reported but are not yet promoted to hard production gates:

- Compound mapping coverage.
- Recommended-compound mapping coverage.
- Pair-context coverage.
- Shared-source pair count.
- Ambiguous mapping rate.
- Quantified-versus-reported occurrence share.
- Evidence-path completeness by entity type.
- Availability of enzyme-state, selectivity, synergy, compound-intelligence, and assay-prioritization sections.

Current packaged mapping metrics:

```text
compound match coverage:              0.6200
recommended compound match coverage:  0.6154
pair context rows:                    293
pairs with shared source context:      30
```

These figures describe coverage, not correctness of efficacy or source utility.

## Benchmark files

```text
outputs_medium/benchmark_report.json
outputs_medium/benchmark_leaderboard.csv
outputs_medium/food_source_mapping_report.json
outputs_medium/aim1_kg_report.json
```

## Interpretation

Passing portfolio gates means the output avoids identified computational failure modes. Food-source coverage means the system found identifier-supported occurrence context for part of the candidate set. Neither establishes extraction feasibility, biological activity, safety, selectivity, or field readiness.
