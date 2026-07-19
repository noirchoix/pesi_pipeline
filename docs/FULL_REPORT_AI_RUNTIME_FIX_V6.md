# PESI full-report and AI runtime fix (v0.5.1)

## Scope

This patch is intentionally limited to the reported runtime defects:

1. Full report JSON failed when nested pandas/numpy artifacts contained `NaN` or infinity.
2. The reports page initiated an automatic request during page initialization and produced an SSR fetch warning.
3. A valid root `.env` was not automatically loaded when the API was started with `uvicorn pesi.api.main:app`.
4. DeepSeek configuration was not visible to the user, making deterministic fallback difficult to diagnose.

## Changes

- Added recursive JSON sanitation at the report, route, HTML appendix, and DeepSeek request boundaries.
- Full and summary reports now convert all non-finite numeric values to JSON `null`.
- Added automatic root `.env` discovery using `python-dotenv`, while preserving process environment precedence.
- DeepSeek client now validates provider, key, model settings, sends strict JSON mode requests, and reports configuration status without exposing the key.
- Report generation is user-triggered after browser mount; `/reports` is client-rendered to avoid server-side access to local browser run state.
- API health and inference options expose safe AI configuration metadata.

## Runtime verification

After restart, check:

```bash
curl -H "X-API-Key: $PESI_API_KEY" http://localhost:8000/api/v1/health
```

Expected AI status when configured:

```json
{"ai":{"enabled":true,"status":"configured","provider":"deepseek","model":"deepseek-chat"}}
```

A generated report should disclose `DeepSeek artifact-grounded synthesis`. If the model request fails, the report remains available and discloses the deterministic fallback plus a non-secret error class.
