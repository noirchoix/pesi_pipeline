# FoodDB Compound and Food-Source Mapping

## Objective

The FoodDB extension answers a narrow research question:

> Is a PESI candidate compound represented in the supplied FoodDB-derived chemistry bundle, and in which foods or ingredients is it reported?

It does not infer efficacy from occurrence.

## Input layout

```text
raw/food_chemistry/
  staging/fooddb.duckdb
  curated/v1/
    compound_descriptors.parquet
    food_compound_edges.parquet
    compound_enzyme_edges.parquet
    compound_pathway_edges.parquet
    ...
```

Discovery also supports `raw/fooddb/food_chemistry`, `raw/fooddb`, and nested DuckDB discovery.

## Mapping policy

`pesi/etl/fooddb_loader.py` applies the following order:

1. Exact InChIKey.
2. Unique connectivity block from the first InChIKey segment.
3. Exact normalized FoodDB primary name.
4. Exact normalized FoodDB synonym.

A candidate is not mapped through unrestricted fuzzy text similarity. Multiple candidates are retained as `ambiguous`, and source confidence is penalized.

## Source evidence

Occurrence rows are grouped by compound and food. They retain:

- FoodDB identifiers.
- Common and scientific food names.
- Food group and subgroup.
- Original and standardized content values where available.
- Preparation type.
- Citation and citation type.
- Count of supporting records.

Occurrence class:

- `quantified_occurrence`: positive content value available.
- `reported_occurrence`: occurrence recorded without a usable positive content value.

## Pair context

For each unique optimized pair, the mapper emits:

- Shared foods containing both mapped compounds.
- Shared quantified-source count.
- Highest shared-source confidence.
- Top individual sources for compound A and compound B.
- Explicit status: shared sources, individual sources only, or no source match.

Pair co-occurrence is contextual. It does not demonstrate that the compounds co-occur in the same preparation, concentration, tissue, extract, or biologically active form.

## KG integration

Added node types:

```text
FoodDBCompound
FoodSource
```

Added relations:

```text
PESI Compound --normalized_to_fooddb_compound--> FoodDBCompound
FoodDBCompound --reported_in_food--> FoodSource
```

SQLite materialized tables:

```text
fooddb_compound_matches
fooddb_food_sources
fooddb_pair_source_context
```

The augmentation is idempotent on `(node_id)` and `(src, dst, rel)`.

## CLI

```bash
python -m pesi.cli.main map-food-sources \
  --raw raw \
  --out outputs_medium \
  --artifact artifacts_medium \
  --top-n-per-compound 30
```

## API

```text
GET /api/v1/inference/food-sources/compound?compound=...
GET /api/v1/inference/food-sources/pair?compound_a=...&compound_b=...
GET /api/v1/results/food-source-report
GET /api/v1/results/fooddb-matches
GET /api/v1/results/food-sources
GET /api/v1/results/pair-food-context
GET /api/v1/results/pair-food-evidence
```

## Scientific boundary

Food/source occurrence is contextual evidence only. It does not establish extractability, dose, efficacy, crop safety, formulation suitability, or field-use readiness.
