PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS markets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  market_id TEXT,
  condition_id TEXT NOT NULL,
  slug TEXT,
  question TEXT,
  category TEXT,
  event_id TEXT,
  event_slug TEXT,
  event_title TEXT,
  active INTEGER,
  closed INTEGER,
  enable_order_book INTEGER,
  accepting_orders INTEGER,
  image_url TEXT,
  icon_url TEXT,
  end_date TEXT,
  start_date TEXT,
  raw_updated_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  UNIQUE(source, condition_id)
);

CREATE TABLE IF NOT EXISTS events (
  source TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_slug TEXT,
  title TEXT,
  category TEXT,
  image_url TEXT,
  icon_url TEXT,
  active INTEGER,
  closed INTEGER,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  raw_json TEXT,
  PRIMARY KEY(source, event_id)
);

CREATE TABLE IF NOT EXISTS market_tokens (
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  outcome TEXT,
  outcome_index INTEGER,
  outcome_price REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(source, token_id)
);

CREATE TABLE IF NOT EXISTS market_outcomes (
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  outcome_index INTEGER NOT NULL,
  outcome TEXT,
  token_id TEXT,
  latest_price REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(source, condition_id, outcome_index)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  volume_total REAL,
  volume_24h REAL,
  volume_7d REAL,
  volume_30d REAL,
  volume_1y REAL,
  volume_clob REAL,
  volume_24h_clob REAL,
  liquidity REAL,
  liquidity_clob REAL,
  outcome_prices_json TEXT,
  raw_json TEXT,
  UNIQUE(source, condition_id, observed_at)
);

CREATE TABLE IF NOT EXISTS event_volume_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  event_id TEXT NOT NULL,
  condition_id TEXT,
  observed_at TEXT NOT NULL,
  total REAL,
  value REAL,
  raw_json TEXT,
  UNIQUE(source, event_id, condition_id, observed_at)
);

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  trade_key TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  trade_ts TEXT NOT NULL,
  side TEXT,
  price REAL,
  size REAL,
  notional REAL,
  fee_rate_bps REAL,
  transaction_hash TEXT,
  raw_json TEXT,
  UNIQUE(source, trade_key)
);

CREATE TABLE IF NOT EXISTS market_volume_aggregates (
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  bucket_size TEXT NOT NULL,
  bucket_start TEXT NOT NULL,
  snapshot_count INTEGER NOT NULL,
  volume_total_open REAL,
  volume_total_close REAL,
  volume_total_delta REAL,
  volume_24h_last REAL,
  liquidity_last REAL,
  trade_count INTEGER NOT NULL DEFAULT 0,
  trade_notional REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(source, condition_id, bucket_size, bucket_start)
);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  condition_id TEXT,
  event_id TEXT,
  title TEXT,
  message TEXT NOT NULL,
  metric_value REAL,
  threshold_value REAL,
  status TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  raw_json TEXT,
  UNIQUE(source, dedupe_key)
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  condition_id TEXT,
  event_id TEXT,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  markets_seen INTEGER DEFAULT 0,
  snapshots_seen INTEGER DEFAULT 0,
  trades_seen INTEGER DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS weather_market_specs (
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  title TEXT NOT NULL,
  city TEXT NOT NULL,
  event_date TEXT NOT NULL,
  metric TEXT NOT NULL,
  comparator TEXT NOT NULL,
  threshold TEXT NOT NULL,
  unit TEXT NOT NULL,
  confidence TEXT NOT NULL,
  parsed_at TEXT NOT NULL,
  spec_json TEXT NOT NULL,
  PRIMARY KEY(source, condition_id)
);

CREATE TABLE IF NOT EXISTS weather_forecast_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  forecast_source TEXT NOT NULL,
  model TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  probability_yes TEXT NOT NULL,
  values_json TEXT NOT NULL,
  raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_order_books (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  outcome TEXT,
  fetched_at TEXT NOT NULL,
  best_bid TEXT,
  best_ask TEXT,
  spread TEXT,
  raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  slug TEXT,
  title TEXT NOT NULL,
  side TEXT NOT NULL,
  model_probability_yes TEXT NOT NULL,
  side_probability TEXT NOT NULL,
  price TEXT NOT NULL,
  edge TEXT NOT NULL,
  expected_return TEXT NOT NULL,
  kelly_fraction TEXT NOT NULL,
  suggested_stake_usd TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  signal_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_paper_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER,
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  title TEXT NOT NULL,
  side TEXT NOT NULL,
  price TEXT NOT NULL,
  quantity TEXT NOT NULL,
  stake_usd TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_settlements (
  source TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  resolved_at TEXT,
  winning_outcome TEXT NOT NULL,
  winning_outcome_index INTEGER NOT NULL,
  winning_token_id TEXT,
  resolution_status TEXT,
  outcome_prices_json TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  PRIMARY KEY(source, condition_id)
);

CREATE INDEX IF NOT EXISTS idx_markets_condition_id ON markets(condition_id);
CREATE INDEX IF NOT EXISTS idx_markets_event_id ON markets(event_id);
CREATE INDEX IF NOT EXISTS idx_events_slug ON events(event_slug);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_condition_observed
  ON market_snapshots(condition_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_event_volume_event_observed
  ON event_volume_snapshots(event_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_trades_condition_ts ON trades(condition_id, trade_ts);
CREATE INDEX IF NOT EXISTS idx_trades_observed_at ON trades(observed_at);
CREATE INDEX IF NOT EXISTS idx_market_volume_aggregates_bucket
  ON market_volume_aggregates(bucket_size, bucket_start);
CREATE INDEX IF NOT EXISTS idx_alerts_status_created
  ON alerts(status, created_at);
CREATE INDEX IF NOT EXISTS idx_data_quality_created
  ON data_quality_issues(created_at);
CREATE INDEX IF NOT EXISTS idx_weather_signals_condition_created
  ON weather_signals(condition_id, created_at);
CREATE INDEX IF NOT EXISTS idx_weather_paper_orders_condition
  ON weather_paper_orders(condition_id);
CREATE INDEX IF NOT EXISTS idx_weather_forecasts_condition_fetched
  ON weather_forecast_snapshots(condition_id, fetched_at);
