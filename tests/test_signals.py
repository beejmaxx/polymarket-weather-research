from __future__ import annotations

from datetime import date
from decimal import Decimal

from pwmk.models.domain import (
    BookLevel,
    Comparator,
    ForecastSnapshot,
    Location,
    MarketSpec,
    OrderBook,
    RawMarket,
    WeatherMetric,
)
from pwmk.trading.risk import RiskLimits
from pwmk.trading.signals import build_signal


def test_builds_yes_signal_when_edge_clears_threshold() -> None:
    market = RawMarket(
        market_id="m1",
        slug="slug",
        title="Will the high temperature in Austin be 80°F or higher on May 8?",
        outcomes=["Yes", "No"],
        clob_token_ids=["yes-token", "no-token"],
    )
    spec = MarketSpec(
        title=market.title,
        city="Austin",
        event_date=date(2026, 5, 8),
        metric=WeatherMetric.HIGH_TEMP,
        comparator=Comparator.AT_OR_ABOVE,
        threshold=Decimal("80"),
        unit="F",
        location=Location(name="Austin", latitude=30.2, longitude=-97.7),
        confidence=Decimal("1"),
    )
    forecast = ForecastSnapshot(
        market_id=market.market_id,
        model="test",
        spec=spec,
        values=[Decimal("81"), Decimal("82"), Decimal("79"), Decimal("83")],
    )
    yes_book = OrderBook(
        token_id="yes-token",
        bids=[BookLevel(price=Decimal("0.50"), size=Decimal("100"))],
        asks=[BookLevel(price=Decimal("0.55"), size=Decimal("100"))],
    )

    signal = build_signal(
        market,
        spec,
        forecast,
        yes_book,
        no_book=None,
        min_edge=Decimal("0.08"),
        max_spread=Decimal("0.08"),
        risk_limits=RiskLimits(
            bankroll_usd=Decimal("1000"),
            max_trade_usd=Decimal("25"),
            max_market_usd=Decimal("50"),
        ),
    )

    assert signal is not None
    assert signal.side.value == "yes"
    assert signal.edge == Decimal("0.20")
    assert signal.suggested_stake_usd > 0
