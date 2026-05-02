from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pwmk.models.domain import (
    ForecastSnapshot,
    MarketSpec,
    OrderBook,
    PaperOrder,
    RawMarket,
    Signal,
)


class ResearchStore:
    def __init__(self, path: str) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def save_raw_market(self, market: RawMarket) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert or replace into raw_markets
                (market_id, slug, title, fetched_at, raw_json)
                values (?, ?, ?, ?, ?)
                """,
                (
                    market.market_id,
                    market.slug,
                    market.title,
                    _utcnow(),
                    _json(market.raw),
                ),
            )

    def save_market_spec(self, market_id: str, spec: MarketSpec) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert or replace into market_specs
                (market_id, title, city, event_date, metric, comparator, threshold, unit,
                 confidence, parsed_at, spec_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market_id,
                    spec.title,
                    spec.city,
                    spec.event_date.isoformat(),
                    spec.metric.value,
                    spec.comparator.value,
                    str(spec.threshold),
                    spec.unit,
                    str(spec.confidence),
                    _utcnow(),
                    _json_model(spec),
                ),
            )

    def save_forecast(self, forecast: ForecastSnapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into forecast_snapshots
                (market_id, source, model, fetched_at, probability_yes, values_json, raw_json)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.market_id,
                    forecast.source,
                    forecast.model,
                    forecast.fetched_at.isoformat(),
                    str(forecast.probability_yes),
                    _json([str(value) for value in forecast.values]),
                    _json(forecast.raw),
                ),
            )

    def save_order_book(self, market_id: str, book: OrderBook) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into order_books
                (market_id, token_id, outcome, fetched_at, best_bid, best_ask, spread, raw_json)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market_id,
                    book.token_id,
                    book.outcome,
                    book.timestamp.isoformat(),
                    _decimal_text(book.best_bid),
                    _decimal_text(book.best_ask),
                    _decimal_text(book.spread),
                    _json(book.raw),
                ),
            )

    def save_signal(self, signal: Signal) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                insert into signals
                (market_id, slug, title, side, model_probability_yes, side_probability,
                 price, edge, expected_return, kelly_fraction, suggested_stake_usd,
                 reason, created_at, signal_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
                    _json_model(signal),
                ),
            )
            return int(cursor.lastrowid)

    def save_paper_order(self, order: PaperOrder) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                insert into paper_orders
                (signal_id, market_id, title, side, price, quantity, stake_usd, status, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.signal_id,
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

    def recent_signals(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select id, created_at, title, side, price, side_probability, edge,
                       expected_return, suggested_stake_usd, reason
                from signals
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return list(rows)


SCHEMA = """
create table if not exists raw_markets (
  market_id text primary key,
  slug text,
  title text not null,
  fetched_at text not null,
  raw_json text not null
);

create table if not exists market_specs (
  market_id text primary key,
  title text not null,
  city text not null,
  event_date text not null,
  metric text not null,
  comparator text not null,
  threshold text not null,
  unit text not null,
  confidence text not null,
  parsed_at text not null,
  spec_json text not null
);

create table if not exists forecast_snapshots (
  id integer primary key autoincrement,
  market_id text,
  source text not null,
  model text not null,
  fetched_at text not null,
  probability_yes text not null,
  values_json text not null,
  raw_json text not null
);

create table if not exists order_books (
  id integer primary key autoincrement,
  market_id text not null,
  token_id text not null,
  outcome text,
  fetched_at text not null,
  best_bid text,
  best_ask text,
  spread text,
  raw_json text not null
);

create table if not exists signals (
  id integer primary key autoincrement,
  market_id text not null,
  slug text,
  title text not null,
  side text not null,
  model_probability_yes text not null,
  side_probability text not null,
  price text not null,
  edge text not null,
  expected_return text not null,
  kelly_fraction text not null,
  suggested_stake_usd text not null,
  reason text not null,
  created_at text not null,
  signal_json text not null
);

create table if not exists paper_orders (
  id integer primary key autoincrement,
  signal_id integer,
  market_id text not null,
  title text not null,
  side text not null,
  price text not null,
  quantity text not null,
  stake_usd text not null,
  status text not null,
  created_at text not null
);
"""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _json_model(model: BaseModel) -> str:
    return model.model_dump_json()


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
