from __future__ import annotations

from decimal import Decimal

from pwmk.models.domain import (
    ContractSide,
    ForecastSnapshot,
    MarketSpec,
    OrderBook,
    RawMarket,
    Signal,
)
from pwmk.trading.probability import expected_return_on_stake, kelly_fraction_binary
from pwmk.trading.risk import RiskLimits


def build_signal(
    market: RawMarket,
    spec: MarketSpec,
    forecast: ForecastSnapshot,
    yes_book: OrderBook | None,
    no_book: OrderBook | None,
    *,
    min_edge: Decimal,
    max_spread: Decimal,
    risk_limits: RiskLimits,
) -> Signal | None:
    probability_yes = forecast.probability_yes
    candidates: list[Signal] = []

    if yes_book and yes_book.best_ask is not None:
        signal = _candidate(
            market=market,
            spec=spec,
            side=ContractSide.YES,
            probability_yes=probability_yes,
            side_probability=probability_yes,
            price=yes_book.best_ask,
            spread=yes_book.spread,
            min_edge=min_edge,
            max_spread=max_spread,
            risk_limits=risk_limits,
        )
        if signal:
            candidates.append(signal)

    if no_book and no_book.best_ask is not None:
        probability_no = Decimal("1") - probability_yes
        signal = _candidate(
            market=market,
            spec=spec,
            side=ContractSide.NO,
            probability_yes=probability_yes,
            side_probability=probability_no,
            price=no_book.best_ask,
            spread=no_book.spread,
            min_edge=min_edge,
            max_spread=max_spread,
            risk_limits=risk_limits,
        )
        if signal:
            candidates.append(signal)

    if not candidates:
        return None
    return max(candidates, key=lambda item: item.expected_return)


def _candidate(
    *,
    market: RawMarket,
    spec: MarketSpec,
    side: ContractSide,
    probability_yes: Decimal,
    side_probability: Decimal,
    price: Decimal,
    spread: Decimal | None,
    min_edge: Decimal,
    max_spread: Decimal,
    risk_limits: RiskLimits,
) -> Signal | None:
    if spread is None or spread > max_spread:
        return None
    edge = side_probability - price
    if edge < min_edge:
        return None
    expected_return = expected_return_on_stake(side_probability, price)
    kelly_fraction = kelly_fraction_binary(side_probability, price)
    stake = risk_limits.stake_for_kelly(kelly_fraction)
    if stake <= 0:
        return None
    return Signal(
        market_id=market.condition_id or market.market_id,
        slug=market.slug,
        title=market.title,
        side=side,
        model_probability_yes=probability_yes,
        side_probability=side_probability,
        price=price,
        edge=edge,
        expected_return=expected_return,
        kelly_fraction=kelly_fraction,
        suggested_stake_usd=stake,
        reason=f"{side.value.upper()} edge {edge:.3f} at {price:.3f}",
        spec=spec,
    )


def paper_order_quantity(stake_usd: Decimal, price: Decimal) -> Decimal:
    if price <= 0:
        return Decimal("0")
    return (stake_usd / price).quantize(Decimal("0.0001"))
