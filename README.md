# PESI-KG Production Research Platform

**PESI-KG** is a computational plant-enzymology platform for selective enzyme-state intervention research. It combines a typed knowledge graph, enzyme-state signatures, critical-transition target ranking, natural/inhibitor-like compound-pair screening, scenario selectivity, evidence-path reconstruction, and artifact-grounded scientific interpretation.

Current application version: **0.5.0**.

## Scientific boundary

PESI generates **computational hypotheses and screening priorities**. It does not establish pesticide efficacy, formulation suitability, application rate, crop safety, extractability from a food source, environmental safety, or regulatory readiness. All candidate pairs require target-specific biochemical assays, comparative crop/weed testing, toxicity review, environmental validation, and regulatory assessment.

Food/source occurrence is contextual evidence only. A reported compound occurrence in a food or ingredient does not establish useful concentration, extraction feasibility, intervention efficacy, or field-use suitability.

## Product workflow

The application is organized around the researcher’s task rather than backend implementation labels:

```text
New analysis
→ friendly run progress
→ recommendations and target insights
→ evidence path and natural-source context
→ DeepSeek-backed or deterministic grounded explanation
→ readable scientific report
→ developer diagnostics
```

The main UI exposes:

- Crop, weed, growth-stage, and analysis-goal setup.
- Run-bound recommendation and target results.
- Enzyme-state reasoning and scenario-selectivity interpretation.
- Pairing/synergy rationale translated into user-facing language.
- Compound-pool intelligence, proxy assumptions, and scientific limitations.
- FoodDB-derived compound-to-food occurrence context.
- Recommendation evidence paths from compound pair to target, family, pathway, stage, inhibitor class, and source evidence.
- Assay-prioritization simulation bands explicitly separated from dose or application guidance.
- JSON and HTML scientific reports.
- Separate diagnostics for raw artifacts, benchmark gates, mapping tables, and logs.

## Implemented research modules

- Typed plant enzyme-state knowledge graph with source provenance.
- Enzyme-state signature evaluation against family/target baselines.
- Critical-transition enzyme ranking with herbicide-target priors.
- Chemically constrained compound-pair optimization.
- Herbicide target atlas and site-of-action context.
- Phytochemical classification and portfolio diversity controls.
- Typed inhibit-synergy groups.
- Crop-versus-weed scenario selectivity.
- Compound-pool screening intelligence and explicit proxy registers.
- Pseudo-lab response simulation for assay prioritization only.
- FoodDB-derived compound normalization and food/ingredient occurrence mapping.
- Pair-level shared and individual natural-source context.
- Evidence-path API and evidence-aware report generation.
- FastAPI orchestration and SvelteKit inference UI.
- Optional server-side DeepSeek interpretation with deterministic artifact-grounded fallback.

## Food chemistry data layout

Place the extracted food chemistry bundle at:

```text
raw/food_chemistry/
  staging/fooddb.duckdb
  curated/v1/*.parquet
```

The loader also supports legacy layouts under `raw/fooddb/` and discovers nested `fooddb.duckdb` files when necessary.

Generate or refresh FoodDB mapping artifacts independently:

```bash
python -m pesi.cli.main map-food-sources \
  --raw raw \
  --out outputs_medium \
  --artifact artifacts_medium \
  --top-n-per-compound 30
```

Generated outputs:

```text
compound_fooddb_matches.csv
compound_food_sources.csv
pair_food_source_context.csv
pair_food_source_evidence.csv
food_source_mapping_report.json
```

The current packaged medium artifacts map 248 of 400 compound-pool records and 40 of 65 compounds used in the recommendation portfolio. Thirty pair records have at least one shared FoodDB food-source context. Unmatched compounds remain explicit; no source claim is inferred from chemical class alone.

## Backend quick start

```bash
python -m pip install -e .
python -m pesi.cli.main run-all \
  --raw raw \
  --out outputs \
  --artifact artifacts \
  --sabio-mode cache \
  --profile audit
python -m pesi.cli.main benchmark --out outputs --artifact artifacts
```

Food-source mapping runs automatically after compound-pair optimization when the food chemistry bundle is available. Configure retained food-source records with:

```env
PESI_FOOD_SOURCE_TOP_N=30
```

## API server

```bash
cp .env.example .env
# Set a private PESI_API_KEY before shared deployment.
uvicorn pesi.api.main:app --host 0.0.0.0 --port 8000
```

API documentation:

```text
http://localhost:8000/api/v1/docs
```

Primary inference endpoints:

```text
GET    /api/v1/inference/options
POST   /api/v1/inference/analyses
GET    /api/v1/inference/analyses/{run_id}/progress
GET    /api/v1/inference/results
POST   /api/v1/inference/explain/recommendation
POST   /api/v1/inference/explain/target
POST   /api/v1/inference/reports

GET    /api/v1/inference/recommendations/{recommendation_id}/evidence-path
GET    /api/v1/inference/targets/{target_id}/state-reasoning
GET    /api/v1/inference/food-sources/compound
GET    /api/v1/inference/food-sources/pair
```

Diagnostics/raw-result endpoints include:

```text
GET /api/v1/results/food-source-report
GET /api/v1/results/fooddb-matches
GET /api/v1/results/food-sources
GET /api/v1/results/pair-food-context
GET /api/v1/results/pair-food-evidence
GET /api/v1/results/proxy-evidence
GET /api/v1/results/pseudo-lab
```

## SvelteKit application

```bash
cd apps/web
npm ci
cp .env.example .env
npm run check
npm run dev
```

Open `http://localhost:5173`.

The browser uses a same-origin SvelteKit proxy at `/api/pesi/*`; the proxy forwards requests to FastAPI server-side. Model-provider secrets are never placed in `VITE_*` variables.

## Optional DeepSeek interpretation

DeepSeek is server-side only:

```env
PESI_AI_ENABLED=true
PESI_AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_private_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

When unavailable or disabled, the system returns a deterministic explanation assembled from the same evidence artifacts. The AI provider is not allowed to invent evidence beyond the supplied payload.

## Validation

Validated in this package:

```text
Python compile check: passed
Pytest: 52 non-raw tests passed across isolated validation chunks; 2 dataset-dependent FoodDB tests require raw/food_chemistry
Svelte check: 0 errors, 0 warnings
Svelte production build: passed
FoodDB KG augmentation: idempotency tested
```

Audit and medium computational portfolio gates remain part of diagnostics and benchmark evidence; passing them does not imply biological efficacy.

## Deployment

```bash
cp .env.example .env
docker compose up --build
```

For shared/public deployments:

- Keep `PESI_AUTH_MODE=required`.
- Keep DeepSeek and other provider keys server-side.
- Use the SvelteKit same-origin proxy or a trusted gateway/session layer.
- Mount raw data, outputs, artifacts, and `.pesi_runs` as persistent volumes.
- Apply tenant/user authorization before exposing run artifacts in multi-user environments.

## Documentation

- `docs/FOOD_SOURCE_MAPPING.md`
- `docs/EVIDENCE_PATHS.md`
- `docs/CHANGELOG_FOOD_EVIDENCE_V4.md`
- `docs/FILE_CHANGES_V4.md`
- `docs/COMPOUND_IDENTITY_FOODDB_INVARIANTS_V9.md`
- `docs/data_cards/compound_identity_policy_card.md`
- `DATA_CARD.md`
- `MODEL_CARD.md`
- `BENCHMARK_CARD.md`

## Scientific semantic validation (v0.5.2)

Reports now apply a deterministic scientific consistency gate after artifact aggregation and optional DeepSeek synthesis. The gate separates the weed-minus-crop selectivity difference from the centered ranking index, normalizes FoodDB match states, conservatively classifies evidence tiers, withholds target-atlas inhibitor classes unless target identity is validated, labels assay bands as dimensionless model inputs, and corrects synthesis statements that contradict structured evidence. See `docs/SCIENTIFIC_SEMANTIC_VALIDATION_V7.md`.

## Canonical enzyme identity and evidence-adjusted ranking (v0.6.0)

PESI now normalizes target records through an auditable enzyme-identity registry before target counting, target-atlas annotation, optimization, evidence-path construction, and reporting. Exact identifiers and exact curated aliases are accepted; broad substring matching is prohibited. Reported names and families remain available for audit, while known family conflicts are corrected in canonical outputs.

The release also separates scenario-level crop/weed vulnerability baselines from target-specific selectivity, separates simulation-derived response rank from evidence-adjusted scientific priority, distinguishes FoodDB zero-result states from biological absence, and uses canonical unordered compound-pair keys across optimization and provenance. See `docs/ENZYME_IDENTITY_AND_EVIDENCE_RANKING_V8.md` and `docs/data_cards/enzyme_identity_registry_card.md`.

## Compound identity and FoodDB semantic invariants (v0.7.0)

PESI now assigns structure-backed canonical compound identities before compound deduplication, FoodDB mapping, pair construction, evidence-path generation, and report synthesis. Identity precedence is full InChIKey, RDKit-validated canonical isomeric SMILES, curated source-record identity, and finally an explicitly labelled normalized-name fallback. Invalid SMILES cannot establish structure-backed identity.

FoodDB occurrence rows are joined exclusively through each compound's canonical ID and are emitted only for unique matched mappings. Unmatched or ambiguous compounds cannot inherit occurrence records from a same-name record or from the other member of a compound pair. The report interpreter independently rechecks these invariants, target/selectivity granularity, source-dataset family conflicts, and evidence-adjusted priority before optional DeepSeek synthesis.

Executive synthesis now reports scientific-priority and simulation-coverage counts separately and rejects claims that complete simulation coverage constitutes stronger biological evidence. See `docs/COMPOUND_IDENTITY_FOODDB_INVARIANTS_V9.md` and `docs/data_cards/compound_identity_policy_card.md`.
