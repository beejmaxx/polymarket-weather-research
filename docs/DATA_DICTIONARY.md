# Data Dictionary

## `events`

One row per provider event, keyed by `(source, event_id)`.

## `markets`

One row per market, keyed by `(source, condition_id)`. Contains display metadata, status flags, event links, dates, and first/last seen timestamps.

## `market_outcomes`

Outcome-level representation keyed by `(source, condition_id, outcome_index)`. Stores the label, token ID, latest price, and update timestamp.

## `market_tokens`

Token lookup keyed by `(source, token_id)`. Optimized for mapping WebSocket asset IDs back to market condition IDs.

## `market_snapshots`

Point-in-time market metrics from Gamma: total volume, 24h/7d/30d/1y volume, liquidity, and outcome prices.

## `event_volume_snapshots`

Event-level live volume decomposition from the Data API.

## `trades`

Observed public CLOB trade prints from the market WebSocket stream. This is observed stream data, not an exchange-complete audit ledger.

## `market_volume_aggregates`

Hourly/daily rollups combining snapshot deltas and observed trade counts/notional.

## `alerts`

Operational and market-intelligence alerts, including volume spikes and stale ingestion warnings.

## `data_quality_issues`

Payload and normalization issues such as missing token IDs or future schema drift.

