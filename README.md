# Prediction Market Volume Layer

Production-ready MVP for ingesting and normalizing Polymarket market and volume data into SQLite, then exposing it through a FastAPI API and internal dashboard.

It also includes a weather-market research loop: parse weather titles, fetch ensemble forecasts, create paper signals, ingest resolved outcomes, and report calibration/P&L before any live trading code exists.

## What It Builds

- `markets`: normalized market metadata keyed by Polymarket `conditionId`
- `market_tokens`: CLOB token IDs mapped to outcomes and current outcome prices
- `market_snapshots`: point-in-time volume, liquidity, and price snapshots from Gamma
- `event_volume_snapshots`: live event volume breakdowns from the Data API
- `trades`: observed WebSocket trade prints from the public CLOB market stream
- `weather_*`: weather parser specs, ensemble forecasts, paper signals, paper orders
- `market_settlements`: inferred resolved outcomes from closed Gamma markets
- `events`: normalized event metadata
- `market_outcomes`: normalized outcome rows mapped to token IDs
- `market_volume_aggregates`: hourly/daily rollups
- `alerts`: stale ingestion and volume spike alerts
- `data_quality_issues`: payload quality and schema drift warnings
- Dashboard at `/` and JSON API under `/api/*`

The implementation uses the current public Polymarket API split:

- Gamma API for market discovery: `https://gamma-api.polymarket.com`
- Data API for public analytics/live volume: `https://data-api.polymarket.com`
- CLOB WebSocket for real-time market updates: `wss://ws-subscriptions-clob.polymarket.com/ws/market`

## Setup

```bash
cd /home/bijan/polymarket-weather-research
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

Initialize the database:

```bash
pwmk init-db
```

Fetch a first batch of top active markets:

```bash
pwmk ingest poll --limit 100
```

Run continuous polling:

```bash
pwmk ingest loop --limit 200 --interval 60
```

Run the dashboard with the built-in scheduler:

```bash
pwmk serve --host 127.0.0.1 --port 8000 --scheduler --poll-limit 200 --poll-interval 60
```

Record public CLOB trade prints for the top token IDs already in the database:

```bash
pwmk ingest stream --asset-limit 50 --duration 300
```

Run reconnecting stream windows:

```bash
pwmk ingest stream-loop --asset-limit 200 --window-seconds 300
```

Backfill active and closed market snapshots:

```bash
pwmk ingest backfill --active-limit 1000 --closed-limit 1000
```

Refresh aggregates and alert checks:

```bash
pwmk maintenance
```

Start the dashboard:

```bash
pwmk serve --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000`.

## Weather Research

Parse a candidate weather market title:

```bash
pwmk weather parse-title "Will the high temperature in New York City be 75°F or higher on May 10?"
```

Generate paper signals from active weather markets:

```bash
pwmk weather audit-titles --limit 200 --source both
pwmk weather scan --limit 200
pwmk weather signals --limit 20
```

`audit-titles` is the parser coverage workflow. It reports how many live weather-tagged or keyword-matched markets are currently supported, and gives concrete skip reasons such as `missing_date`, `missing_threshold`, or `unsupported_weather_type`.

Fetch settlements for paper-traded markets once they close:

```bash
pwmk weather sync-settlements --limit 100
```

For a smoke test without existing paper orders, scan recent closed markets:

```bash
pwmk weather sync-settlements --recent-closed --limit 25
```

Report paper-trade calibration and P&L:

```bash
pwmk weather calibration
```

## Useful API Routes

- `GET /api/summary`
- `GET /api/scheduler`
- `GET /api/events?limit=50`
- `GET /api/markets?limit=50&search=bitcoin`
- `GET /api/markets/{condition_id}`
- `GET /api/markets/{condition_id}/volume?hours=24`
- `GET /api/markets/{condition_id}/aggregates?bucket_size=hour&hours=168`
- `GET /api/momentum?limit=25`
- `GET /api/trades?limit=50`
- `GET /api/alerts?status=pending`
- `GET /api/data-quality`
- `GET /api/weather/signals?limit=50`
- `GET /api/weather/settlements?limit=50`
- `GET /api/weather/calibration`
- `GET /api/export/markets.csv?limit=1000`
- `POST /api/ingest/poll?limit=100`
- `POST /api/ingest/backfill?active_limit=1000&closed_limit=1000`
- `POST /api/maintenance`

## Production Controls

Copy `.env.example` to `.env` and set:

```dotenv
PWMK_API_TOKEN=replace-me
PWMK_ENABLE_SCHEDULER=true
PWMK_ENABLE_STREAM=true
PWMK_ALERT_WEBHOOK_URL=
```

When `PWMK_API_TOKEN` is set, API routes require `X-API-Key` or `Authorization: Bearer`.

CSV and JSON exports work with the base install. Parquet export is available from the CLI with:

```bash
pip install -e ".[parquet]"
pwmk export-markets --format parquet --output markets.parquet
```

## Deployment

Docker Compose:

```bash
cp .env.example .env
docker compose up --build -d
```

Systemd and operating docs are in `docs/DEPLOYMENT.md` and `docs/RUNBOOK.md`.
