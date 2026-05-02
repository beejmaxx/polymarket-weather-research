from __future__ import annotations

from datetime import date
from decimal import Decimal

from pwmk.models.domain import Comparator, WeatherMetric
from pwmk.parsing.weather_market_parser import WeatherMarketParser, is_weather_candidate


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


def test_parse_any_rain_market_infers_threshold() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    spec = parser.parse("Will it rain in NYC on May 8?")

    assert spec is not None
    assert spec.city == "New York"
    assert spec.metric is WeatherMetric.PRECIP_SUM
    assert spec.comparator is Comparator.ABOVE
    assert spec.threshold == Decimal("0")
    assert spec.unit == "inch"
    assert "rain_threshold_inferred_any_amount" in spec.notes


def test_parse_lowest_temperature_in_international_city() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    spec = parser.parse("Will the lowest temperature in London be 5°C or below on May 2?")

    assert spec is not None
    assert spec.city == "London"
    assert spec.location is not None
    assert spec.location.timezone == "Europe/London"
    assert spec.metric is WeatherMetric.LOW_TEMP
    assert spec.comparator is Comparator.AT_OR_BELOW
    assert spec.threshold == Decimal("5")
    assert spec.unit == "C"


def test_parse_highest_temperature_in_hong_kong() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    spec = parser.parse("Will the highest temperature in Hong Kong be 25°C or higher on April 30?")

    assert spec is not None
    assert spec.city == "Hong Kong"
    assert spec.location is not None
    assert spec.location.timezone == "Asia/Hong_Kong"
    assert spec.metric is WeatherMetric.HIGH_TEMP
    assert spec.comparator is Comparator.AT_OR_ABOVE
    assert spec.threshold == Decimal("25")
    assert spec.unit == "C"


def test_weather_candidate_uses_word_boundaries() -> None:
    assert is_weather_candidate("Will it rain in Chicago on May 8?")
    assert is_weather_candidate("Will the high temperature in New York be above 80°F on May 8?")
    assert not is_weather_candidate("Russia-Ukraine Ceasefire before GTA VI?")
    assert not is_weather_candidate("Jack Lowdon announced as next James Bond?")


def test_parse_with_reason_explains_rejected_title() -> None:
    parser = WeatherMarketParser(reference_date=date(2026, 5, 2))

    attempt = parser.parse_with_reason("Will a hurricane make landfall in the US by May 31?")

    assert not attempt.parsed
    assert attempt.reason == "unsupported_weather_type"
