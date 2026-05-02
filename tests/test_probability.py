from __future__ import annotations

from datetime import date
from decimal import Decimal

from pwmk.models.domain import Comparator, ForecastSnapshot, Location, MarketSpec, WeatherMetric
from pwmk.trading.probability import brier_score, expected_return_on_stake, kelly_fraction_binary


def test_forecast_probability_uses_comparator() -> None:
    spec = MarketSpec(
        title="x",
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
        model="test", spec=spec, values=[Decimal("79"), Decimal("80"), Decimal("81")]
    )

    assert forecast.probability_yes == Decimal("0.6666666666666666666666666667")


def test_expected_return_and_kelly() -> None:
    assert expected_return_on_stake(Decimal("0.60"), Decimal("0.50")) == Decimal("0.2")
    assert kelly_fraction_binary(Decimal("0.60"), Decimal("0.50")) == Decimal("0.2")
    assert brier_score(Decimal("0.80"), True) == Decimal("0.04")
