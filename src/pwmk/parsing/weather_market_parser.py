from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from pwmk.models.domain import Comparator, MarketSpec, WeatherMetric
from pwmk.parsing.locations import find_known_location

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

MONTH_PATTERN = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_RE = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
    r"(?:,?\s+(?P<year>20\d{2}))?\b",
    re.IGNORECASE,
)
SLASH_DATE_RE = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:/(?P<year>\d{2,4}))?\b")
TEMP_RE = re.compile(
    r"(?P<threshold>-?\d+(?:\.\d+)?)\s*(?:°|degrees?)?\s*(?P<unit>f|fahrenheit|c|celsius)?\b",
    re.IGNORECASE,
)
PRECIP_RE = re.compile(
    r"(?P<threshold>\d+(?:\.\d+)?)\s*(?P<unit>inches|inch|in|mm|millimeters?)\b",
    re.IGNORECASE,
)


class WeatherMarketParser:
    def __init__(self, reference_date: date | None = None) -> None:
        self.reference_date = reference_date or date.today()

    def parse(self, title: str) -> MarketSpec | None:
        normalized = _normalize_title(title)
        if not _looks_weather_related(normalized):
            return None

        notes: list[str] = []
        confidence = Decimal("1.0")

        event_date = self._parse_date(normalized)
        if event_date is None:
            return None

        location = find_known_location(normalized)
        city = location.name if location else _extract_city_fallback(title)
        if not city:
            return None
        if location is None:
            confidence -= Decimal("0.30")
            notes.append("unknown_location_coordinates")

        metric = _parse_metric(normalized)
        if metric is None:
            confidence -= Decimal("0.20")
            metric = WeatherMetric.HIGH_TEMP
            notes.append("metric_inferred_high_temp")

        comparator = _parse_comparator(normalized)
        if comparator is None:
            return None

        threshold, unit = _parse_threshold(normalized, metric)
        if threshold is None:
            return None
        if unit is None:
            unit = "F" if metric in {WeatherMetric.HIGH_TEMP, WeatherMetric.LOW_TEMP} else "inch"
            confidence -= Decimal("0.15")
            notes.append("unit_inferred")

        if metric in {WeatherMetric.HIGH_TEMP, WeatherMetric.LOW_TEMP} and unit.lower() in {
            "f",
            "fahrenheit",
        }:
            unit = "F"
        elif metric in {WeatherMetric.HIGH_TEMP, WeatherMetric.LOW_TEMP}:
            unit = "C"
        elif unit.lower() in {"in", "inch", "inches"}:
            unit = "inch"
        else:
            unit = "mm"

        confidence = max(Decimal("0"), min(confidence, Decimal("1")))
        return MarketSpec(
            title=title,
            city=city,
            event_date=event_date,
            metric=metric,
            comparator=comparator,
            threshold=threshold,
            unit=unit,
            location=location,
            confidence=confidence,
            notes=notes,
        )

    def _parse_date(self, text: str) -> date | None:
        match = DATE_RE.search(text)
        if match:
            year = int(match.group("year")) if match.group("year") else self.reference_date.year
            month = MONTHS[match.group("month").lower().rstrip(".")]
            day = int(match.group("day"))
            parsed = date(year, month, day)
            if match.group("year") is None and (parsed - self.reference_date).days < -30:
                parsed = date(year + 1, month, day)
            return parsed

        match = SLASH_DATE_RE.search(text)
        if not match:
            return None
        year_text = match.group("year")
        year = self.reference_date.year
        if year_text:
            year = int(year_text)
            if year < 100:
                year += 2000
        parsed = date(year, int(match.group("month")), int(match.group("day")))
        if year_text is None and (parsed - self.reference_date).days < -30:
            parsed = date(year + 1, parsed.month, parsed.day)
        return parsed


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.replace("−", "-")).strip().lower()


def _looks_weather_related(text: str) -> bool:
    keywords = (
        "temperature",
        "temp",
        "high",
        "low",
        "hotter",
        "colder",
        "rain",
        "precip",
        "snow",
        "weather",
        "degrees",
        "°",
    )
    return any(keyword in text for keyword in keywords)


def _parse_metric(text: str) -> WeatherMetric | None:
    if any(token in text for token in ("rain", "precipitation", "precip")):
        return WeatherMetric.PRECIP_SUM
    if any(token in text for token in (" low ", "minimum", "min temp", "overnight low", "colder")):
        return WeatherMetric.LOW_TEMP
    if any(token in text for token in (" high ", "maximum", "max temp", "hit", "reach", "hotter")):
        return WeatherMetric.HIGH_TEMP
    return None


def _parse_comparator(text: str) -> Comparator | None:
    if any(token in text for token in ("or higher", "at least", "reach", "hit", "hotter")):
        return Comparator.AT_OR_ABOVE
    if any(token in text for token in ("above", "over", "exceed", "greater than")):
        return Comparator.ABOVE
    if any(token in text for token in ("or lower", "at most", "no more than")):
        return Comparator.AT_OR_BELOW
    if any(token in text for token in ("below", "under", "less than", "colder")):
        return Comparator.BELOW
    return None


def _parse_threshold(text: str, metric: WeatherMetric) -> tuple[Decimal | None, str | None]:
    regex = PRECIP_RE if metric is WeatherMetric.PRECIP_SUM else TEMP_RE
    matches = list(regex.finditer(text))
    if not matches:
        return None, None

    # Prefer the number nearest comparator language instead of dates.
    for match in matches:
        before = text[max(0, match.start() - 30) : match.start()]
        after = text[match.end() : match.end() + 30]
        if any(
            word in before + after
            for word in ("above", "below", "over", "under", "higher", "lower")
        ):
            return Decimal(match.group("threshold")), match.group("unit")
    match = matches[0]
    return Decimal(match.group("threshold")), match.group("unit")


def _extract_city_fallback(title: str) -> str | None:
    match = re.search(
        r"\b(?:in|for)\s+([A-Z][A-Za-z .'-]+?)"
        r"(?=\s+(?:on|by|be|above|below|over|under|reach|hit)\b|[?,]|$)",
        title,
    )
    if not match:
        return None
    city = match.group(1).strip()
    return city if len(city) >= 2 else None
