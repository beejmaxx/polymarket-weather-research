from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from pwmk.models.domain import (
    ForecastSnapshot,
    MarketSettlement,
    MarketSpec,
    OrderBook,
    PaperOrder,
    Signal,
)
from pwmk.parsing.normalize import as_float, compact_json, utc_now_iso


def _schema_sql() -> str:
    return Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def _cutoff_iso(hours: int) -> str:
    return (
        (datetime.now(UTC) - timedelta(hours=hours))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _calibration_from_rows(rows: list[sqlite3.Row], unsettled: int) -> dict[str, Any]:
    total_stake = Decimal("0")
    total_payoff = Decimal("0")
    brier_sum = Decimal("0")
    wins = 0
    bins: dict[int, dict[str, Decimal | int]] = {
        idx: {
            "count": 0,
            "probability_sum": Decimal("0"),
            "actual_sum": Decimal("0"),
            "brier_sum": Decimal("0"),
        }
        for idx in range(10)
    }

    for row in rows:
        stake = _decimal(row["stake_usd"])
        quantity = _decimal(row["quantity"])
        probability_yes = _decimal(row["model_probability_yes"])
        winning_outcome = str(row["winning_outcome"]).lower()
        side = str(row["side"]).lower()
        actual_yes = Decimal("1") if winning_outcome == "yes" else Decimal("0")
        won = side == winning_outcome
        payoff = quantity if won else Decimal("0")
        brier = (probability_yes - actual_yes) ** 2

        total_stake += stake
        total_payoff += payoff
        brier_sum += brier
        wins += int(won)

        bin_idx = min(9, max(0, int(probability_yes * 10)))
        bucket = bins[bin_idx]
        bucket["count"] = int(bucket["count"]) + 1
        bucket["probability_sum"] = Decimal(bucket["probability_sum"]) + probability_yes
        bucket["actual_sum"] = Decimal(bucket["actual_sum"]) + actual_yes
        bucket["brier_sum"] = Decimal(bucket["brier_sum"]) + brier

    count = len(rows)
    pnl = total_payoff - total_stake
    return {
        "settled_orders": count,
        "unsettled_orders": unsettled,
        "wins": wins,
        "win_rate": _ratio(wins, count),
        "stake_usd": _money(total_stake),
        "payoff_usd": _money(total_payoff),
        "pnl_usd": _money(pnl),
        "roi": _ratio_decimal(pnl, total_stake),
        "brier_score": _ratio_decimal(brier_sum, Decimal(count)),
        "bins": [_format_bin(idx, bucket) for idx, bucket in bins.items() if bucket["count"]],
    }


def _format_bin(idx: int, bucket: dict[str, Decimal | int]) -> dict[str, Any]:
    count = int(bucket["count"])
    return {
        "bin": f"{idx / 10:.1f}-{(idx + 1) / 10:.1f}",
        "count": count,
        "avg_probability": _ratio_decimal(Decimal(bucket["probability_sum"]), Decimal(count)),
        "actual_rate": _ratio_decimal(Decimal(bucket["actual_sum"]), Decimal(count)),
        "brier_score": _ratio_decimal(Decimal(bucket["brier_sum"]), Decimal(count)),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _ratio_decimal(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator / denominator), 6)


def _money(value: Decimal) -> float:
    return round(float(value), 4)


def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_schema_sql())


class Repository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def start_run(self, mode: str) -> int:
        started_at = utc_now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ingestion_runs(mode, started_at, status)
                VALUES (?, ?, 'running')
                """,
                (mode, started_at),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        markets_seen: int = 0,
        snapshots_seen: int = 0,
        trades_seen: int = 0,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ingestion_runs
                SET finished_at = ?, status = ?, markets_seen = ?, snapshots_seen = ?,
                    trades_seen = ?, error = ?
                WHERE id = ?
                """,
                (
                    utc_now_iso(),
                    status,
                    markets_seen,
                    snapshots_seen,
                    trades_seen,
                    error,
                    run_id,
                ),
            )

    def save_market_bundle(self, bundles: list[dict[str, Any]]) -> tuple[int, int, int]:
        market_count = 0
        snapshot_count = 0
        token_count = 0
        with self.connect() as conn:
            for bundle in bundles:
                market = bundle["market"]
                snapshot = bundle["snapshot"]
                conn.execute(
                    """
                    INSERT INTO markets(
                      source, market_id, condition_id, slug, question, category, event_id,
                      event_slug, event_title, active, closed, enable_order_book,
                      accepting_orders, image_url, icon_url, end_date, start_date,
                      raw_updated_at, first_seen_at, last_seen_at
                    )
                    VALUES (
                      :source, :market_id, :condition_id, :slug, :question, :category,
                      :event_id, :event_slug, :event_title, :active, :closed,
                      :enable_order_book, :accepting_orders, :image_url, :icon_url,
                      :end_date, :start_date, :raw_updated_at, :observed_at, :observed_at
                    )
                    ON CONFLICT(source, condition_id) DO UPDATE SET
                      market_id = excluded.market_id,
                      slug = excluded.slug,
                      question = excluded.question,
                      category = excluded.category,
                      event_id = excluded.event_id,
                      event_slug = excluded.event_slug,
                      event_title = excluded.event_title,
                      active = excluded.active,
                      closed = excluded.closed,
                      enable_order_book = excluded.enable_order_book,
                      accepting_orders = excluded.accepting_orders,
                      image_url = excluded.image_url,
                      icon_url = excluded.icon_url,
                      end_date = excluded.end_date,
                      start_date = excluded.start_date,
                      raw_updated_at = excluded.raw_updated_at,
                      last_seen_at = excluded.last_seen_at
                    """,
                    market,
                )
                market_count += 1

                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO market_snapshots(
                      source, condition_id, observed_at, volume_total, volume_24h,
                      volume_7d, volume_30d, volume_1y, volume_clob, volume_24h_clob,
                      liquidity, liquidity_clob, outcome_prices_json, raw_json
                    )
                    VALUES (
                      :source, :condition_id, :observed_at, :volume_total, :volume_24h,
                      :volume_7d, :volume_30d, :volume_1y, :volume_clob,
                      :volume_24h_clob, :liquidity, :liquidity_clob,
                      :outcome_prices_json, :raw_json
                    )
                    """,
                    snapshot,
                )
                snapshot_count += cursor.rowcount

                for token in bundle["tokens"]:
                    conn.execute(
                        """
                        INSERT INTO market_tokens(
                          source, condition_id, token_id, outcome, outcome_index,
                          outcome_price, updated_at
                        )
                        VALUES (
                          :source, :condition_id, :token_id, :outcome, :outcome_index,
                          :outcome_price, :updated_at
                        )
                        ON CONFLICT(source, token_id) DO UPDATE SET
                          condition_id = excluded.condition_id,
                          outcome = excluded.outcome,
                          outcome_index = excluded.outcome_index,
                          outcome_price = excluded.outcome_price,
                          updated_at = excluded.updated_at
                        """,
                        token,
                    )
                    token_count += 1
        return market_count, snapshot_count, token_count

    def save_event_volume(
        self, event_id: str, payload: list[dict[str, Any]], observed_at: str
    ) -> int:
        rows = 0
        with self.connect() as conn:
            for item in payload:
                total = as_float(item.get("total"))
                for market in item.get("markets", []):
                    condition_id = market.get("market")
                    if not condition_id:
                        continue
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO event_volume_snapshots(
                          source, event_id, condition_id, observed_at, total, value, raw_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "polymarket",
                            str(event_id),
                            str(condition_id),
                            observed_at,
                            total,
                            as_float(market.get("value")),
                            compact_json(item),
                        ),
                    )
                    rows += cursor.rowcount
        return rows

    def save_trade(self, trade: dict[str, Any]) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO trades(
                  source, trade_key, condition_id, asset_id, observed_at, trade_ts, side,
                  price, size, notional, fee_rate_bps, transaction_hash, raw_json
                )
                VALUES (
                  :source, :trade_key, :condition_id, :asset_id, :observed_at,
                  :trade_ts, :side, :price, :size, :notional, :fee_rate_bps,
                  :transaction_hash, :raw_json
                )
                """,
                trade,
            )
            return cursor.rowcount == 1

    def save_weather_market_spec(self, condition_id: str, spec: MarketSpec) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO weather_market_specs(
                  source, condition_id, title, city, event_date, metric, comparator,
                  threshold, unit, confidence, parsed_at, spec_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, condition_id) DO UPDATE SET
                  title = excluded.title,
                  city = excluded.city,
                  event_date = excluded.event_date,
                  metric = excluded.metric,
                  comparator = excluded.comparator,
                  threshold = excluded.threshold,
                  unit = excluded.unit,
                  confidence = excluded.confidence,
                  parsed_at = excluded.parsed_at,
                  spec_json = excluded.spec_json
                """,
                (
                    "polymarket",
                    condition_id,
                    spec.title,
                    spec.city,
                    spec.event_date.isoformat(),
                    spec.metric.value,
                    spec.comparator.value,
                    str(spec.threshold),
                    spec.unit,
                    str(spec.confidence),
                    utc_now_iso(),
                    spec.model_dump_json(),
                ),
            )

    def save_weather_forecast(self, condition_id: str, forecast: ForecastSnapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO weather_forecast_snapshots(
                  source, condition_id, forecast_source, model, fetched_at,
                  probability_yes, values_json, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "polymarket",
                    condition_id,
                    forecast.source,
                    forecast.model,
                    forecast.fetched_at.isoformat(),
                    str(forecast.probability_yes),
                    compact_json([str(value) for value in forecast.values]),
                    compact_json(forecast.raw),
                ),
            )

    def save_weather_order_book(self, condition_id: str, book: OrderBook) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO weather_order_books(
                  source, condition_id, token_id, outcome, fetched_at, best_bid,
                  best_ask, spread, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "polymarket",
                    condition_id,
                    book.token_id,
                    book.outcome,
                    book.timestamp.isoformat(),
                    _decimal_text(book.best_bid),
                    _decimal_text(book.best_ask),
                    _decimal_text(book.spread),
                    compact_json(book.raw),
                ),
            )

    def save_weather_signal(self, signal: Signal) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO weather_signals(
                  source, condition_id, slug, title, side, model_probability_yes,
                  side_probability, price, edge, expected_return, kelly_fraction,
                  suggested_stake_usd, reason, created_at, signal_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "polymarket",
                    signal.market_id,
                    signal.slug,
                    signal.title,
                    signal.side.value,
                    str(signal.model_probability_yes),
                    str(signal.side_probability),
                    str(signal.price),
                    str(signal.edge),
                    str(signal.expected_return),
                    str(signal.kelly_fraction),
                    str(signal.suggested_stake_usd),
                    signal.reason,
                    signal.created_at.isoformat(),
                    signal.model_dump_json(),
                ),
            )
            return int(cursor.lastrowid)

    def save_weather_paper_order(self, order: PaperOrder) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO weather_paper_orders(
                  signal_id, source, condition_id, title, side, price, quantity,
                  stake_usd, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.signal_id,
                    "polymarket",
                    order.market_id,
                    order.title,
                    order.side.value,
                    str(order.price),
                    str(order.quantity),
                    str(order.stake_usd),
                    order.status,
                    order.created_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def save_market_settlement(self, settlement: MarketSettlement) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO market_settlements(
                  source, condition_id, resolved_at, winning_outcome,
                  winning_outcome_index, winning_token_id, resolution_status,
                  outcome_prices_json, raw_json, observed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, condition_id) DO UPDATE SET
                  resolved_at = excluded.resolved_at,
                  winning_outcome = excluded.winning_outcome,
                  winning_outcome_index = excluded.winning_outcome_index,
                  winning_token_id = excluded.winning_token_id,
                  resolution_status = excluded.resolution_status,
                  outcome_prices_json = excluded.outcome_prices_json,
                  raw_json = excluded.raw_json,
                  observed_at = excluded.observed_at
                """,
                (
                    "polymarket",
                    settlement.condition_id,
                    settlement.resolved_at.isoformat() if settlement.resolved_at else None,
                    settlement.winning_outcome,
                    settlement.winning_outcome_index,
                    settlement.winning_token_id,
                    settlement.resolution_status,
                    compact_json([str(price) for price in settlement.outcome_prices]),
                    compact_json(settlement.raw),
                    settlement.observed_at.isoformat(),
                ),
            )
            conn.execute(
                """
                UPDATE weather_paper_orders
                SET status = 'settled'
                WHERE source = 'polymarket' AND condition_id = ?
                """,
                (settlement.condition_id,),
            )

    def recent_weather_signals(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, condition_id, title, side, price,
                       side_probability, edge, expected_return, suggested_stake_usd, reason
                FROM weather_signals
                WHERE source = 'polymarket'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def unsettled_weather_condition_ids(self, limit: int = 100) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT po.condition_id
                FROM weather_paper_orders po
                LEFT JOIN market_settlements ms
                  ON ms.source = po.source AND ms.condition_id = po.condition_id
                WHERE po.source = 'polymarket' AND ms.condition_id IS NULL
                ORDER BY po.created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [str(row["condition_id"]) for row in rows]

    def recent_settlements(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT condition_id, resolved_at, winning_outcome, winning_outcome_index,
                       winning_token_id, resolution_status, observed_at
                FROM market_settlements
                WHERE source = 'polymarket'
                ORDER BY COALESCE(resolved_at, observed_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def weather_calibration_report(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  po.id AS order_id,
                  po.side,
                  po.price,
                  po.quantity,
                  po.stake_usd,
                  s.model_probability_yes,
                  s.side_probability,
                  st.winning_outcome,
                  po.title
                FROM weather_paper_orders po
                JOIN weather_signals s
                  ON s.source = po.source AND s.id = po.signal_id
                JOIN market_settlements st
                  ON st.source = po.source AND st.condition_id = po.condition_id
                WHERE po.source = 'polymarket'
                ORDER BY po.id ASC
                """
            ).fetchall()
            unsettled = conn.execute(
                """
                SELECT count(*) AS count
                FROM weather_paper_orders po
                LEFT JOIN market_settlements st
                  ON st.source = po.source AND st.condition_id = po.condition_id
                WHERE po.source = 'polymarket' AND st.condition_id IS NULL
                """
            ).fetchone()["count"]

        return _calibration_from_rows(rows, int(unsettled))

    def list_token_map(self, limit: int = 50) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH latest AS (
                  SELECT ms.*
                  FROM market_snapshots ms
                  JOIN (
                    SELECT source, condition_id, max(observed_at) AS observed_at
                    FROM market_snapshots
                    GROUP BY source, condition_id
                  ) last
                    ON last.source = ms.source
                   AND last.condition_id = ms.condition_id
                   AND last.observed_at = ms.observed_at
                )
                SELECT t.token_id, t.condition_id
                FROM market_tokens t
                JOIN markets m
                  ON m.source = t.source AND m.condition_id = t.condition_id
                LEFT JOIN latest l
                  ON l.source = t.source AND l.condition_id = t.condition_id
                WHERE m.active = 1 AND m.closed = 0
                ORDER BY COALESCE(l.volume_24h, 0) DESC, t.outcome_index ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return {str(row["token_id"]): str(row["condition_id"]) for row in rows}

    def list_markets(
        self,
        *,
        limit: int = 50,
        search: str | None = None,
        active: bool | None = True,
        sort: str = "volume24h",
    ) -> list[dict[str, Any]]:
        sort_sql = {
            "volume24h": "COALESCE(l.volume_24h, 0) DESC",
            "volumeTotal": "COALESCE(l.volume_total, 0) DESC",
            "liquidity": "COALESCE(l.liquidity, 0) DESC",
            "updated": "COALESCE(l.observed_at, m.last_seen_at) DESC",
        }.get(sort, "COALESCE(l.volume_24h, 0) DESC")

        where = ["1 = 1"]
        params: dict[str, Any] = {"limit": limit}
        if search:
            where.append("(lower(m.question) LIKE :search OR lower(m.slug) LIKE :search)")
            params["search"] = f"%{search.lower()}%"
        if active is not None:
            where.append("m.active = :active AND m.closed = 0")
            params["active"] = int(active)

        sql = f"""
            WITH latest AS (
              SELECT ms.*
              FROM market_snapshots ms
              JOIN (
                SELECT source, condition_id, max(observed_at) AS observed_at
                FROM market_snapshots
                GROUP BY source, condition_id
              ) last
                ON last.source = ms.source
               AND last.condition_id = ms.condition_id
               AND last.observed_at = ms.observed_at
            )
            SELECT
              m.*,
              l.observed_at AS latest_observed_at,
              l.volume_total,
              l.volume_24h,
              l.volume_7d,
              l.volume_30d,
              l.volume_1y,
              l.volume_clob,
              l.volume_24h_clob,
              l.liquidity,
              l.liquidity_clob,
              l.outcome_prices_json
            FROM markets m
            LEFT JOIN latest l
              ON l.source = m.source AND l.condition_id = m.condition_id
            WHERE {" AND ".join(where)}
            ORDER BY {sort_sql}
            LIMIT :limit
        """
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def get_market(self, condition_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            market = conn.execute(
                """
                WITH latest AS (
                  SELECT *
                  FROM market_snapshots
                  WHERE source = 'polymarket' AND condition_id = ?
                  ORDER BY observed_at DESC
                  LIMIT 1
                )
                SELECT
                  m.*,
                  l.observed_at AS latest_observed_at,
                  l.volume_total,
                  l.volume_24h,
                  l.volume_7d,
                  l.volume_30d,
                  l.volume_1y,
                  l.volume_clob,
                  l.volume_24h_clob,
                  l.liquidity,
                  l.liquidity_clob,
                  l.outcome_prices_json
                FROM markets m
                LEFT JOIN latest l
                  ON l.source = m.source AND l.condition_id = m.condition_id
                WHERE m.source = 'polymarket' AND m.condition_id = ?
                """,
                (condition_id, condition_id),
            ).fetchone()
            if market is None:
                return None

            data = dict(market)
            data["tokens"] = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT token_id, outcome, outcome_index, outcome_price, updated_at
                    FROM market_tokens
                    WHERE source = 'polymarket' AND condition_id = ?
                    ORDER BY outcome_index ASC
                    """,
                    (condition_id,),
                ).fetchall()
            ]
            data["recent_trades"] = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT trade_ts, side, price, size, notional, transaction_hash, asset_id
                    FROM trades
                    WHERE source = 'polymarket' AND condition_id = ?
                    ORDER BY trade_ts DESC
                    LIMIT 20
                    """,
                    (condition_id,),
                ).fetchall()
            ]
            return data

    def volume_series(self, condition_id: str, hours: int = 24) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT observed_at, volume_total, volume_24h, volume_7d, volume_30d, liquidity
                FROM market_snapshots
                WHERE source = 'polymarket'
                  AND condition_id = ?
                  AND observed_at >= ?
                ORDER BY observed_at ASC
                """,
                (condition_id, _cutoff_iso(hours)),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  t.trade_ts, t.condition_id, t.asset_id, t.side, t.price, t.size,
                  t.notional, t.transaction_hash, m.question, mt.outcome
                FROM trades t
                LEFT JOIN markets m
                  ON m.source = t.source AND m.condition_id = t.condition_id
                LEFT JOIN market_tokens mt
                  ON mt.source = t.source AND mt.token_id = t.asset_id
                WHERE t.source = 'polymarket'
                ORDER BY t.trade_ts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        cutoff = _cutoff_iso(24)
        with self.connect() as conn:
            row = conn.execute(
                """
                WITH latest AS (
                  SELECT ms.*
                  FROM market_snapshots ms
                  JOIN (
                    SELECT source, condition_id, max(observed_at) AS observed_at
                    FROM market_snapshots
                    GROUP BY source, condition_id
                  ) last
                    ON last.source = ms.source
                   AND last.condition_id = ms.condition_id
                   AND last.observed_at = ms.observed_at
                )
                SELECT
                  count(m.id) AS total_markets,
                  sum(CASE WHEN m.active = 1 AND m.closed = 0 THEN 1 ELSE 0 END)
                    AS active_markets,
                  COALESCE(sum(CASE WHEN m.active = 1 AND m.closed = 0
                    THEN l.volume_24h ELSE 0 END), 0) AS active_volume_24h,
                  COALESCE(sum(CASE WHEN m.active = 1 AND m.closed = 0
                    THEN l.volume_total ELSE 0 END), 0) AS active_volume_total,
                  COALESCE(sum(CASE WHEN m.active = 1 AND m.closed = 0
                    THEN l.liquidity ELSE 0 END), 0) AS active_liquidity,
                  max(l.observed_at) AS latest_snapshot_at
                FROM markets m
                LEFT JOIN latest l
                  ON l.source = m.source AND l.condition_id = m.condition_id
                """
            ).fetchone()
            trades_row = conn.execute(
                """
                SELECT
                  count(*) AS trades_total,
                  COALESCE(sum(CASE WHEN observed_at >= ? THEN 1 ELSE 0 END), 0) AS trades_24h,
                  COALESCE(sum(CASE WHEN observed_at >= ? THEN notional ELSE 0 END), 0)
                    AS observed_notional_24h
                FROM trades
                WHERE source = 'polymarket'
                """,
                (cutoff, cutoff),
            ).fetchone()
            last_run = conn.execute(
                """
                SELECT mode, started_at, finished_at, status, markets_seen, snapshots_seen,
                       trades_seen, error
                FROM ingestion_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        data = _row_to_dict(row) or {}
        data.update(_row_to_dict(trades_row) or {})
        data["last_run"] = _row_to_dict(last_run)
        data["db_path"] = str(self.db_path)
        return data

    def export_markets_json(self, limit: int = 1000) -> str:
        return json.dumps(self.list_markets(limit=limit, active=None), indent=2)
