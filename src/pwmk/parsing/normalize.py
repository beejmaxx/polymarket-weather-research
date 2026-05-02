from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def timestamp_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        number = number / 1000
    return (
        datetime.fromtimestamp(number, UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if not isinstance(value, str):
        return []

    text = value.strip()
    for _ in range(2):
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            text = parsed.strip()
            continue
        return []
    return []


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return 1
        if lowered in {"false", "0", "no"}:
            return 0
    return int(bool(value))


def compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def normalize_market(raw: dict[str, Any], observed_at: str | None = None) -> dict[str, Any]:
    observed_at = observed_at or utc_now_iso()
    condition_id = raw.get("conditionId") or raw.get("condition_id")
    if not condition_id:
        raise ValueError("Market is missing conditionId")

    events = raw.get("events")
    event = events[0] if isinstance(events, list) and events else {}
    outcomes = [str(item) for item in parse_json_array(raw.get("outcomes"))]
    prices = [as_float(item) for item in parse_json_array(raw.get("outcomePrices"))]
    token_ids = [str(item) for item in parse_json_array(raw.get("clobTokenIds"))]

    market = {
        "source": "polymarket",
        "market_id": str(raw.get("id")) if raw.get("id") is not None else None,
        "condition_id": str(condition_id),
        "slug": raw.get("slug"),
        "question": raw.get("question"),
        "category": raw.get("category") or event.get("category"),
        "event_id": str(event.get("id")) if event.get("id") is not None else None,
        "event_slug": event.get("slug"),
        "event_title": event.get("title"),
        "active": as_bool(raw.get("active")),
        "closed": as_bool(raw.get("closed")),
        "enable_order_book": as_bool(raw.get("enableOrderBook")),
        "accepting_orders": as_bool(raw.get("acceptingOrders")),
        "image_url": raw.get("image"),
        "icon_url": raw.get("icon"),
        "end_date": raw.get("endDate") or raw.get("endDateIso"),
        "start_date": raw.get("startDate") or raw.get("startDateIso"),
        "raw_updated_at": raw.get("updatedAt"),
        "observed_at": observed_at,
    }

    snapshot = {
        "source": "polymarket",
        "condition_id": str(condition_id),
        "observed_at": observed_at,
        "volume_total": as_float(raw.get("volumeNum") or raw.get("volume")),
        "volume_24h": as_float(raw.get("volume24hr")),
        "volume_7d": as_float(raw.get("volume1wk")),
        "volume_30d": as_float(raw.get("volume1mo")),
        "volume_1y": as_float(raw.get("volume1yr")),
        "volume_clob": as_float(raw.get("volumeClob")),
        "volume_24h_clob": as_float(raw.get("volume24hrClob")),
        "liquidity": as_float(raw.get("liquidityNum") or raw.get("liquidity")),
        "liquidity_clob": as_float(raw.get("liquidityClob")),
        "outcome_prices_json": compact_json(prices),
        "raw_json": compact_json(raw),
    }

    token_rows: list[dict[str, Any]] = []
    for index, token_id in enumerate(token_ids):
        token_rows.append(
            {
                "source": "polymarket",
                "condition_id": str(condition_id),
                "token_id": token_id,
                "outcome": outcomes[index] if index < len(outcomes) else None,
                "outcome_index": index,
                "outcome_price": prices[index] if index < len(prices) else None,
                "updated_at": observed_at,
            }
        )

    return {"market": market, "snapshot": snapshot, "tokens": token_rows}


def normalize_trade_event(
    event: dict[str, Any],
    token_to_condition: dict[str, str] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any] | None:
    if event.get("event_type") != "last_trade_price":
        return None

    observed_at = observed_at or utc_now_iso()
    token_to_condition = token_to_condition or {}
    asset_id = str(event.get("asset_id") or "")
    condition_id = event.get("market") or token_to_condition.get(asset_id)
    if not asset_id or not condition_id:
        return None

    price = as_float(event.get("price"))
    size = as_float(event.get("size"))
    notional = price * size if price is not None and size is not None else None
    trade_ts = timestamp_to_iso(event.get("timestamp")) or observed_at
    trade_key_source = compact_json(
        {
            "asset_id": asset_id,
            "market": condition_id,
            "price": event.get("price"),
            "size": event.get("size"),
            "timestamp": event.get("timestamp"),
            "transaction_hash": event.get("transaction_hash"),
        }
    )
    trade_key = hashlib.sha256(trade_key_source.encode("utf-8")).hexdigest()

    return {
        "source": "polymarket",
        "trade_key": trade_key,
        "condition_id": str(condition_id),
        "asset_id": asset_id,
        "observed_at": observed_at,
        "trade_ts": trade_ts,
        "side": event.get("side"),
        "price": price,
        "size": size,
        "notional": notional,
        "fee_rate_bps": as_float(event.get("fee_rate_bps")),
        "transaction_hash": event.get("transaction_hash"),
        "raw_json": compact_json(event),
    }
