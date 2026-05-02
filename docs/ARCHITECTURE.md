# Architecture

The service is split into four layers.

## Collectors

- `pwmk.clients.polymarket`: public Gamma/Data/CLOB endpoints used by the volume layer.
- `pwmk.collectors.*`: weather research collectors used by the optional weather workflow.
- `pwmk.providers.*`: provider interface that keeps Polymarket-specific code swappable.

## Normalization

Raw provider payloads are normalized into stable internal tables:

- market metadata
- events
- outcomes/tokens
- market snapshots
- event volume snapshots
- trades
- hourly/daily aggregates
- alerts and data-quality issues

Raw payloads are retained where useful for debugging upstream API drift.

## Storage

SQLite is the default because it keeps the MVP easy to run and deploy. The repository layer isolates SQL access so a future Postgres/TimescaleDB migration can keep the same API and dashboard surface.

## API And Dashboard

FastAPI exposes JSON routes under `/api/*` and serves the internal dashboard from `/`. Optional token auth is enabled by setting `PWMK_API_TOKEN`.

## Background Runtime

The API process can run an internal scheduler:

- market polling every `PWMK_POLL_INTERVAL_SECONDS`
- optional reconnecting WebSocket trade stream windows
- aggregate refresh
- alert checks and optional webhook delivery

