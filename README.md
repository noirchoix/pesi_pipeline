# PESI-KG Production Research Backend

**PESI-KG** = Plant Enzyme-State Intervention Knowledge Graph.

This build upgrades PESI from a runnable v2 scaffold into a production-oriented PhD research backend for:

```text
Computational Plant Enzymology for Selective Enzyme-State Intervention
```

The flagship use case is **bioherbicide / herbicide-biology-aware selection of naturally derived inhibitor combinations** against critical plant enzyme-state transitions.

## What is implemented

### Aim 1 — Plant enzyme-state KG

- PlantCyc / PlantMetWiki / CAZy / FoodDB ingestion.
- BKMS and UniProt↔Rhea reaction mapping.
- SKiD and SABIO-RK kinetic evidence integration.
- Curated enzyme-family workbooks with corrected `curated_family` handling.
- Source-table persistence and typed KG outputs.

### Aim 2 — Enzyme-state signatures

- Feature construction from pathway, kinetic, structural, plant-context, inhibitor-availability, and trajectory-curvature signals.
- Signature clustering and comparison against family / target-class baselines.

### Aim 3 — Critical transition enzyme ranking

- Formula + weak-label ML criticality model.
- Semantic de-duplication of enzyme-name variants.
- Explicit evidence classes and uncertainty penalties.

### Aim 4 — Chemically credible inhibitor-combination optimization

The optimizer now includes:

- `intervention_suitability_score`
- `compound_priority_class`
- `compound_exclusion_reason`
- solvent / buffer / generic assay chemical penalties
- reactive aldehyde control penalties
- FoodDB / natural-product evidence priority
- known herbicide-like and transition-state mimic scores
- active-site compatibility score
- herbicide target atlas matching
- contextual crop/weed selectivity proxy
- typed inhibit-synergy graph
- unordered compound-pair de-duplication
- per-target diversity cap

### Herbicide target atlas

Implemented in:

```text
pesi/domain/herbicide_targets.py
data/reference/herbicide_target_reference.csv
```

Includes rules for:

```text
ALS/AHAS
EPSPS
ACCase
PPO
PSII
PSI
Glutamine synthetase
Tubulin / microtubule assembly
VLCFA biosynthesis
CAZy / cell-wall metabolism
Cytochrome P450 detoxification
Oxidative stress enzymes
```

### Scenario selectivity model

Implemented in:

```text
pesi/domain/selectivity.py
pesi/schemas/scenario.py
pesi/integrations/plantid_client.py
```

Selectivity is scenario-based, not universal. A “weed” is modeled relative to a field scenario:

```text
crop taxa + crop family + visually/API-identified weed taxa + growth stage + location
```

Plant.id support is available via `PLANT_ID_API_KEY` but is optional.

### Benchmarks

Implemented in:

```text
pesi/benchmarks/evaluate.py
python -m pesi.cli.main benchmark
```

Outputs:

```text
outputs/benchmark_report.json
outputs/benchmark_leaderboard.csv
```

Benchmark categories include:

- enzyme-state signatures vs family / target-class labels
- criticality model vs random / herbicide-target baselines
- optimizer diversity and compound-quality checks
- synergy graph vs Bliss-only proxy
- target diversity and control-compound rate

## Quick start

```bash
python -m pip install -e .
python -m pesi.cli.main bootstrap --source-dir /path/to/Downloads --raw raw --force
python -m pesi.cli.main fetch-sabio \
  --raw raw \
  --queries "ParameterType:Ki" \
  --queries "ParameterType:Km" \
  --queries "ParameterType:kcat" \
  --page-size 200 \
  --max-pages 10
python -m pesi.cli.main run-all --raw raw --out outputs --artifact artifacts --sabio-mode cache --profile audit
python -m pesi.cli.main benchmark --out outputs --artifact artifacts
```

Run profiles:

```bash
python -m pesi.cli.main run-all --profile audit
python -m pesi.cli.main run-all --profile medium
python -m pesi.cli.main run-all --profile large
python -m pesi.cli.main run-all --profile full
```

`--full` is retained as a deprecated alias for `--profile full`.

## API

```bash
uvicorn pesi.api.main:app --host 0.0.0.0 --port 8000
```

Endpoints:

```text
/health
/reports/run-manifest
/critical-enzymes
/optimized-interventions
/synergy-groups
/pseudo-lab
/benchmarks
```

## Plant.id integration

Set your API key outside the repository:

```bash
export PLANT_ID_API_KEY="your_key"
```

Then use `pesi.integrations.plantid_client.PlantIdClient` to identify crop/weed taxa from images and convert them into a field scenario.

## Scientific status

The system is a production-oriented computational research backend. It does **not** claim wet-lab validation.

Outputs explicitly distinguish:

```text
real_evidence
proxy_evidence
model_inference
pseudo_lab_model_inference
contextual_model_inference_requires_crop_weed_assay_validation
```

The intended validation path is:

```text
KG/ML target ranking
→ compound suitability and synergy graph ranking
→ enzyme inhibition assays
→ crop/weed dose-response assays
→ field-context selectivity evaluation
```

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

## Important safety and research notes

This software generates computational research hypotheses. It is not a pesticide label, application recommendation, environmental safety approval, or regulatory submission by itself. Candidate combinations require toxicity, persistence, crop injury, non-target organism, and field validation before any practical use.
