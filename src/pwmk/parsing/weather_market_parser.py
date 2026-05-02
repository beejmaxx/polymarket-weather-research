from __future__ import annotations

import re
from dataclasses import dataclass
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
WEATHER_CANDIDATE_RE = re.compile(
    r"(\bweather\b|\btemperatures?\b|\btemps?\b|\brain\b|\brainfall\b|"
    r"\bprecip(?:itation)?\b|\bsnow\b|\bdegrees?\b|°|\bhurricanes?\b|"
    r"\bstorms?\b|\bhottest\b|\bcoldest\b|\bhotter\b|\bcolder\b|"
    r"\bhigh temperature\b|\blow temperature\b|\barctic sea ice\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParseAttempt:
    title: str
    spec: MarketSpec | None
    reason: str

    @property
    def parsed(self) -> bool:
        return self.spec is not None


class WeatherMarketParser:
    def __init__(self, reference_date: date | None = None) -> None:
        self.reference_date = reference_date or date.today()

    def parse(self, title: str) -> MarketSpec | None:
        return self.parse_with_reason(title).spec

    def parse_with_reason(self, title: str) -> ParseAttempt:
        normalized = _normalize_title(title)
        if not _looks_weather_related(normalized):
            return ParseAttempt(title=title, spec=None, reason="not_weather_candidate")

        notes: list[str] = []
        confidence = Decimal("1.0")

        event_date = self._parse_date(normalized)
        if event_date is None:
            return ParseAttempt(title=title, spec=None, reason="missing_date")

        metric = _parse_metric(normalized)
        if metric is None:
            if _is_unsupported_weather_type(normalized):
                return ParseAttempt(title=title, spec=None, reason="unsupported_weather_type")
            confidence -= Decimal("0.20")
            metric = WeatherMetric.HIGH_TEMP
            notes.append("metric_inferred_high_temp")

        location = find_known_location(normalized)
        city = location.name if location else _extract_city_fallback(title)
        if not city:
            return ParseAttempt(title=title, spec=None, reason="missing_location")
        if location is None:
            confidence -= Decimal("0.30")
            notes.append("unknown_location_coordinates")

        comparator = _parse_comparator(normalized)
        if comparator is None:
            comparator = _infer_comparator(normalized, metric)
        if comparator is None:
            return ParseAttempt(title=title, spec=None, reason="missing_comparator")

        threshold, unit = _parse_threshold(normalized, metric)
        if (
            threshold is None
            and metric is WeatherMetric.PRECIP_SUM
            and _asks_if_any_rain(normalized)
        ):
            threshold = Decimal("0")
            unit = "inch"
            comparator = Comparator.ABOVE
            confidence -= Decimal("0.10")
            notes.append("rain_threshold_inferred_any_amount")
        if threshold is None:
            return ParseAttempt(title=title, spec=None, reason="missing_threshold")
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
        spec = MarketSpec(
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
        return ParseAttempt(title=title, spec=spec, reason="parsed")

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
    return is_weather_candidate(text)


def is_weather_candidate(title: str) -> bool:
    return WEATHER_CANDIDATE_RE.search(title) is not None


def _parse_metric(text: str) -> WeatherMetric | None:
    if re.search(r"\b(rain|rainfall|precip|precipitation)\b", text):
        return WeatherMetric.PRECIP_SUM
    if any(
        token in text
        for token in (
            " low ",
            "low temperature",
            "lowest temperature",
            "minimum",
            "min temp",
            "overnight low",
            "colder",
        )
    ):
        return WeatherMetric.LOW_TEMP
    if any(
        token in text
        for token in (
            " high ",
            "high temperature",
            "highest temperature",
            "maximum",
            "max temp",
            "hit",
            "reach",
            "hotter",
            "degrees",
            "°",
        )
    ):
        return WeatherMetric.HIGH_TEMP
    return None


def _is_unsupported_weather_type(text: str) -> bool:
    return (
        re.search(
            r"\b(hurricane|storm|sea ice|earthquake|volcano|meteor|disaster|landfall)\b", text
        )
        is not None
    )


def _parse_comparator(text: str) -> Comparator | None:
    if any(
        token in text for token in ("or higher", "or above", "at least", "reach", "hit", "hotter")
    ):
        return Comparator.AT_OR_ABOVE
    if any(token in text for token in ("above", "over", "exceed", "greater than")):
        return Comparator.ABOVE
    if any(token in text for token in ("or lower", "or below", "at most", "no more than")):
        return Comparator.AT_OR_BELOW
    if any(token in text for token in ("below", "under", "less than", "colder")):
        return Comparator.BELOW
    return None


def _infer_comparator(text: str, metric: WeatherMetric) -> Comparator | None:
    if metric is WeatherMetric.PRECIP_SUM and _asks_if_any_rain(text):
        return Comparator.ABOVE
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


def _asks_if_any_rain(text: str) -> bool:
    return re.search(r"\b(will|does|do|did|is)\b.*\brain\b", text) is not None


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
