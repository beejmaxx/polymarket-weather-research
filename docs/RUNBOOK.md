# Runbook

## Start Locally

```bash
source .venv/bin/activate
pwmk init-db
pwmk ingest poll --limit 200
pwmk serve --host 127.0.0.1 --port 8000 --scheduler
```

## Backfill

```bash
pwmk ingest backfill --active-limit 1000 --closed-limit 1000
```

## Stream Trades

```bash
pwmk ingest stream-loop --asset-limit 200 --window-seconds 300
```

## Refresh Analytics

```bash
pwmk maintenance
```

## Ingestion Is Stale

1. Check `/api/summary` and `/api/scheduler`.
2. Review recent `ingestion_runs` via the dashboard status or SQLite.
3. Run `pwmk ingest poll --limit 50` manually.
4. If it fails, inspect upstream API errors and network access.

## WebSocket Has No Trades

This can be normal during quiet windows. Run with a higher asset limit or longer window:

```bash
pwmk ingest stream --asset-limit 200 --duration 600
```

