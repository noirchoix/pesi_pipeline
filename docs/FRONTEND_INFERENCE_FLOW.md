# PESI Inference Product Flow

This frontend version is organized around a user-facing inference workflow rather than backend observability.

## Product flow

1. **New Analysis** — user sets crop, weed, growth stage, and analysis goal.
2. **Run** — user starts the backend and sees friendly progress, not terminal output.
3. **Results** — user reviews candidate compound pairs, important enzyme targets, scenario notes, evidence strength, and pairing signals.
4. **Explain** — user opens a recommendation or target and receives readable rationale. If `PESI_AI_ENABLED=true` and `DEEPSEEK_API_KEY` are configured on the backend, the rationale is DeepSeek-assisted; otherwise the API returns a deterministic artifact-grounded fallback.
5. **Report** — user exports a readable research-use report.
6. **Diagnostics** — developer-only backend outputs, raw checks, raw tables, and logs.

## Key design rule

The main product pages must not expose backend-first language such as raw benchmark gates, Aim numbers, terminal logs, row counts, or artifact filenames. Those belong in Diagnostics.

## Backend endpoints added

- `GET /api/v1/inference/options`
- `POST /api/v1/inference/analyses`
- `GET /api/v1/inference/analyses/{run_id}/progress`
- `GET /api/v1/inference/results`
- `POST /api/v1/inference/explain/recommendation`
- `POST /api/v1/inference/explain/target`
- `POST /api/v1/inference/reports`

## Environment

DeepSeek keys must stay server-side:

```env
PESI_AI_ENABLED=true
PESI_AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

Do not place provider keys in `VITE_*` variables.
