# PESI-KG API Contract

Base path: `/api/v1`

## Authentication

Set `PESI_API_KEY` and `PESI_AUTH_MODE=required`. Provide either:

```text
X-API-Key: <key>
Authorization: Bearer <key>
```

## Run lifecycle

`POST /runs` returns HTTP 202 and a run record. The run executes in a background thread using the existing CLI commands.

Statuses:

```text
queued -> running -> succeeded | failed
```

Logs are available through `/runs/{run_id}/logs`.

## Result endpoints

All result endpoints are read-only and return either JSON artifacts or paginated CSV records. Query parameters include `limit`, `offset`, and route-specific filters.

## Interpretation endpoints

Interpretation endpoints return structured JSON. They do not use unconstrained free generation; they ground responses in generated artifact columns and mandatory scientific caveats.
