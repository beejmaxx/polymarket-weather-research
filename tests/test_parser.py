from __future__ import annotations

from datetime import date
from decimal import Decimal

from pwmk.models.domain import Comparator, WeatherMetric
from pwmk.parsing.weather_market_parser import WeatherMarketParser


def test_parse_high_temperature_market() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    spec = parser.parse("Will the high temperature in New York City be 75°F or higher on May 10?")

    assert spec is not None
    assert spec.city == "New York"
    assert spec.event_date == date(2026, 5, 10)
    assert spec.metric is WeatherMetric.HIGH_TEMP
    assert spec.comparator is Comparator.AT_OR_ABOVE
    assert spec.threshold == Decimal("75")
    assert spec.unit == "F"
    assert spec.location is not None


def test_parse_low_temperature_market() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    spec = parser.parse("Will the low temperature in Chicago be below 40 degrees F on May 8?")

    assert spec is not None
    assert spec.city == "Chicago"
    assert spec.metric is WeatherMetric.LOW_TEMP
    assert spec.comparator is Comparator.BELOW
    assert spec.threshold == Decimal("40")


def test_unknown_location_lowers_confidence() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    spec = parser.parse("Will the high temperature in Testville be above 80°F on May 8?")

    assert spec is not None
    assert spec.location is None
    assert spec.confidence < Decimal("1")
