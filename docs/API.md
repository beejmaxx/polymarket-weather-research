# API

All API routes are unauthenticated by default. Set `PWMK_API_TOKEN` to require either:

- `X-API-Key: <token>`
- `Authorization: Bearer <token>`

## Core Routes

- `GET /api/health`
- `GET /api/summary`
- `GET /api/scheduler`
- `GET /api/events?limit=50`
- `GET /api/markets?limit=50&search=bitcoin&sort=volume24h`
- `GET /api/markets/{condition_id}`
- `GET /api/markets/{condition_id}/volume?hours=24`
- `GET /api/markets/{condition_id}/aggregates?bucket_size=hour&hours=168`
- `GET /api/momentum?limit=25`
- `GET /api/trades?limit=50`
- `GET /api/alerts?status=pending`
- `GET /api/data-quality`

## Admin Routes

- `POST /api/ingest/poll?limit=200`
- `POST /api/ingest/backfill?active_limit=1000&closed_limit=1000`
- `POST /api/maintenance`

## Exports

- `GET /api/export/markets.json?limit=1000`
- `GET /api/export/markets.csv?limit=1000`
- `GET /api/export/trades.csv?limit=1000`

CLI-only Parquet export is available with the optional `parquet` extra:

```bash
pwmk export-markets --format parquet --output markets.parquet
```
