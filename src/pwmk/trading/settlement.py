from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pwmk.models.domain import MarketSettlement
from pwmk.parsing.normalize import parse_json_array


def infer_market_settlement(
    raw: dict[str, Any],
    *,
    observed_at: datetime | None = None,
    decisive_price: Decimal = Decimal("0.99"),
) -> MarketSettlement | None:
    if not raw.get("closed"):
        return None

    condition_id = raw.get("conditionId") or raw.get("condition_id")
    if not condition_id:
        return None

    outcomes = [str(item) for item in parse_json_array(raw.get("outcomes"))]
    prices = [_decimal_or_none(item) for item in parse_json_array(raw.get("outcomePrices"))]
    token_ids = [str(item) for item in parse_json_array(raw.get("clobTokenIds"))]
    if not outcomes or not prices or len(outcomes) != len(prices):
        return None

    winners = [
        idx for idx, price in enumerate(prices) if price is not None and price >= decisive_price
    ]
    if len(winners) != 1:
        return None

    winner_idx = winners[0]
    resolved_at = _parse_datetime(
        raw.get("closedTime") or raw.get("umaEndDate") or raw.get("updatedAt")
    )
    observed_at = observed_at or datetime.now(UTC)
    return MarketSettlement(
        condition_id=str(condition_id),
        resolved_at=resolved_at,
        winning_outcome=outcomes[winner_idx],
        winning_outcome_index=winner_idx,
        winning_token_id=token_ids[winner_idx] if winner_idx < len(token_ids) else None,
        resolution_status=raw.get("umaResolutionStatus"),
        outcome_prices=[price if price is not None else Decimal("0") for price in prices],
        observed_at=observed_at,
        raw=raw,
    )


def paper_order_pnl(
    *,
    side: str,
    winning_outcome: str,
    stake_usd: Decimal,
    quantity: Decimal,
) -> Decimal:
    won = side.strip().lower() == winning_outcome.strip().lower()
    payoff = quantity if won else Decimal("0")
    return payoff - stake_usd


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
