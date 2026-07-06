# PESI-KG Production Research Platform

**PESI-KG** = Plant Enzyme-State Intervention Knowledge Graph.

This repository is the locked production research baseline plus application layer for:

```text
Computational Plant Enzymology for Selective Enzyme-State Intervention
```

The flagship use case is herbicide-biology-aware computational prioritization of naturally derived or inhibitor-like compound combinations against critical plant enzyme-state transitions.

## Scientific status and safety boundary

This system generates **computational hypotheses** and ranked intervention candidates.

It does **not** claim wet-lab pesticide efficacy. It does **not** provide field-use, formulation, dosing, application, or regulatory recommendations. All Aim 4 outputs require experimental validation, toxicity review, crop-safety testing, environmental persistence assessment, and regulatory review before any real-world use.

## Locked validation baseline

The current backend passed both audit and medium production gates.

| Profile | Gates | Key Aim 4 portfolio metrics |
| --- | ---: | --- |
| audit | 7/7 | 1000 rows, 41 targets, 72 compounds, 298 unique pairs, max compound share 0.09 |
| medium | 7/7 | 1000 rows, 43 targets, 65 compounds, 292 unique pairs, max compound share 0.09 |

Medium profile used expanded source bounds: UniProt 10,000, CAZy 25,000, PlantMet edges 50,000, PlantCyc triples 50,000, enzyme-SMI pairs 33,739, and SABIO cache 6,000.

## Implemented research modules

- Aim 1: typed plant enzyme-state KG with source provenance.
- Aim 2: enzyme-state signature evaluation versus family and target-class baselines.
- Aim 3: critical transition enzyme ranking with strict high-confidence known-target enrichment.
- Aim 4: chemically credible inhibitor-combination optimization.
- Herbicide target atlas and site-of-action annotations.
- Phytochemical/chemical-class annotation and diversity constraints.
- Typed inhibit-synergy graph.
- Scenario selectivity layer for crop-vs-weed context.
- Production benchmark gates and leaderboard.
- FastAPI run orchestration and result API.
- SvelteKit research console UI.
- Artifact-grounded interpretation and HTML/JSON report generation.

## Backend quick start

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

## API server

```bash
export PESI_API_KEY="change-me-before-production"
export PESI_AUTH_MODE=required
uvicorn pesi.api.main:app --host 0.0.0.0 --port 8000
```

API documentation:

```text
http://localhost:8000/api/v1/docs
```

Core endpoints:

```text
POST   /api/v1/runs
GET    /api/v1/runs
GET    /api/v1/runs/{run_id}
GET    /api/v1/runs/{run_id}/logs
GET    /api/v1/runs/{run_id}/artifacts

GET    /api/v1/results/kg-summary
GET    /api/v1/results/aim2
GET    /api/v1/results/aim2-signatures
GET    /api/v1/results/aim3
GET    /api/v1/results/aim4
GET    /api/v1/results/synergy
GET    /api/v1/results/scenario-selectivity
GET    /api/v1/results/compound-pool

GET    /api/v1/benchmarks/summary
GET    /api/v1/benchmarks/leaderboard
GET    /api/v1/benchmarks/gates
GET    /api/v1/benchmarks/report

POST   /api/v1/interpret/run
POST   /api/v1/interpret/intervention
POST   /api/v1/interpret/target
POST   /api/v1/interpret/synergy-group
POST   /api/v1/reports
GET    /api/v1/reports/{report_id}.html
```

Example run request:

```json
{
  "profile": "audit",
  "sabio_mode": "cache",
  "raw_dir": "raw",
  "out_dir": "outputs",
  "artifact_dir": "artifacts",
  "scenario": {
    "crop_taxa": ["Zea mays"],
    "weed_taxa": ["Amaranthus palmeri"],
    "growth_stage": "seedling_emergence"
  }
}
```

## SvelteKit research console

```bash
cd apps/web
npm install
cp .env.example .env
npm run dev
```

Open:

```text
http://localhost:5173
```

The UI includes:

- Dashboard with production gates and portfolio metrics.
- Run launcher and live run-log monitor.
- KG source and node/edge summary.
- Aim 2 signature explorer.
- Aim 3 critical-target explorer.
- Aim 4 intervention cards with expandable scientific evidence.
- Synergy-group explorer.
- Scenario selectivity screen.
- Benchmark gate page.
- Artifact-grounded report page.

## Docker Compose

```bash
cp .env.example .env
# edit PESI_API_KEY before production
 docker compose up --build
```

API: `http://localhost:8000/api/v1/docs`
Web: `http://localhost:4173`

## Authentication and deployment

- Set `PESI_API_KEY` and `PESI_AUTH_MODE=required` for shared deployments.
- The UI sends `VITE_PESI_API_KEY` to the API; use this only for internal/private deployments.
- For public multi-user deployments, place the SvelteKit app behind a server-side session/auth provider and proxy API requests server-side rather than exposing API keys to browsers.
- Keep raw data, outputs, artifacts, and `.pesi_runs` mounted as persistent volumes.

## Evidence policy

Outputs explicitly label proxy assumptions, model inference, rule-based evidence, and assay-validation requirements. The interpretation layer reads only generated run artifacts and reference tables before producing structured JSON/HTML.

## Git baseline lock

Recommended local lock commands:

```bash
git status
git add .
git commit -m "Lock PESI-KG production research baseline with audit and medium gate pass"
git tag v0.3.0-production-research-baseline
```

The application version is `0.4.0` because it adds FastAPI/SvelteKit/reporting around the locked `v0.3.0` research baseline.
