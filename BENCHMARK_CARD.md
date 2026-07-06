# PESI-KG Benchmark Card

## Benchmark purpose

Production gates verify that PESI-KG outputs are structurally valid and scientifically constrained enough for computational research workflows.

## Gate families

1. Strict known-target enrichment is available and above baseline.
2. Solvent/reactive/generic control candidates are excluded from final pairs.
3. Target-family entropy is high enough to avoid family collapse.
4. Developmental-stage entropy preserves lifecycle coverage.
5. Individual compound concentration is capped.
6. Compound portfolio breadth is maintained.
7. Target portfolio breadth is maintained.

## Locked results

Audit and medium profiles both passed all seven gates in the validated baseline.

## Benchmark files

```text
outputs/benchmark_report.json
outputs/benchmark_leaderboard.csv
outputs_medium/benchmark_report.json
outputs_medium/benchmark_leaderboard.csv
```

When audit outputs are not present in a package, regenerate them with:

```bash
python -m pesi.cli.main run-all --raw raw --out outputs --artifact artifacts --sabio-mode cache --profile audit
python -m pesi.cli.main benchmark --out outputs --artifact artifacts
```

## Interpretation

Passing gates does not imply wet-lab efficacy. Passing gates means the computational portfolio avoids major structural failure modes: repeated compounds, weak target spread, family collapse, control-compound dominance, and missing strict target enrichment.
