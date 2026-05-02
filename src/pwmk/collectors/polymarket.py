from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pwmk.models.domain import BookLevel, OrderBook, RawMarket

WEATHER_KEYWORDS = ("weather", "temperature", "rain", "snow", "degrees", "°", "hotter", "colder")


class PolymarketClient:
    def __init__(self, gamma_base_url: str, clob_base_url: str, timeout: float = 20.0) -> None:
        self.gamma_base_url = gamma_base_url.rstrip("/")
        self.clob_base_url = clob_base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_active_markets(self, limit: int = 200, offset: int = 0) -> list[RawMarket]:
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "offset": offset,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.gamma_base_url}/markets", params=params)
            response.raise_for_status()
            payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("markets", [])
        return [parse_raw_market(row) for row in rows]

    async def fetch_closed_markets(self, limit: int = 200, offset: int = 0) -> list[RawMarket]:
        params = {
            "closed": "true",
            "limit": limit,
            "offset": offset,
            "order": "updatedAt",
            "ascending": "false",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.gamma_base_url}/markets", params=params)
            response.raise_for_status()
            payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("markets", [])
        return [parse_raw_market(row) for row in rows]

    async def fetch_closed_market_by_condition(self, condition_id: str) -> RawMarket | None:
        params = {"condition_ids": condition_id, "closed": "true"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.gamma_base_url}/markets", params=params)
            response.raise_for_status()
            payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("markets", [])
        return parse_raw_market(rows[0]) if rows else None

    async def fetch_weather_markets(self, limit: int = 200, offset: int = 0) -> list[RawMarket]:
        markets = await self.fetch_active_markets(limit=limit, offset=offset)
        return [market for market in markets if _looks_weather_market(market.title)]

    async def fetch_order_book(self, token_id: str, outcome: str | None = None) -> OrderBook:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.clob_base_url}/book", params={"token_id": token_id})
            response.raise_for_status()
            payload = response.json()
        return parse_order_book(token_id, payload, outcome=outcome)


def parse_raw_market(row: dict[str, Any]) -> RawMarket:
    outcomes = _json_list(row.get("outcomes"))
    outcome_prices = [_to_decimal(value) for value in _json_list(row.get("outcomePrices"))]
    token_ids = _json_list(row.get("clobTokenIds") or row.get("clobTokenIDs"))
    title = row.get("question") or row.get("title") or row.get("name") or ""
    return RawMarket(
        market_id=str(row.get("id") or row.get("conditionId") or row.get("slug") or title),
        slug=row.get("slug"),
        title=title,
        condition_id=row.get("conditionId"),
        active=bool(row.get("active", True)),
        closed=bool(row.get("closed", False)),
        enable_order_book=bool(row.get("enableOrderBook", False)),
        outcomes=[str(item) for item in outcomes],
        outcome_prices=[value for value in outcome_prices if value is not None],
        clob_token_ids=[str(item) for item in token_ids],
        raw=row,
    )


def parse_order_book(
    token_id: str, payload: dict[str, Any], outcome: str | None = None
) -> OrderBook:
    timestamp = _parse_timestamp(payload.get("timestamp"))
    return OrderBook(
        token_id=token_id,
        market=payload.get("market"),
        outcome=outcome,
        timestamp=timestamp,
        bids=[
            BookLevel(price=Decimal(item["price"]), size=Decimal(item["size"]))
            for item in payload.get("bids", [])
        ],
        asks=[
            BookLevel(price=Decimal(item["price"]), size=Decimal(item["size"]))
            for item in payload.get("asks", [])
        ],
        min_order_size=_to_decimal(payload.get("min_order_size")),
        tick_size=_to_decimal(payload.get("tick_size")),
        raw=payload,
    )


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _looks_weather_market(title: str) -> bool:
    normalized = title.lower()
    return any(keyword in normalized for keyword in WEATHER_KEYWORDS)


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    text = str(value)
    if text.isdigit():
        raw = int(text)
        if raw > 10_000_000_000:
            raw = raw // 1000
        return datetime.fromtimestamp(raw, UTC)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
