from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Comparator(StrEnum):
    ABOVE = "above"
    AT_OR_ABOVE = "at_or_above"
    BELOW = "below"
    AT_OR_BELOW = "at_or_below"

    def test(self, value: Decimal, threshold: Decimal) -> bool:
        if self is Comparator.ABOVE:
            return value > threshold
        if self is Comparator.AT_OR_ABOVE:
            return value >= threshold
        if self is Comparator.BELOW:
            return value < threshold
        if self is Comparator.AT_OR_BELOW:
            return value <= threshold
        raise ValueError(f"Unhandled comparator: {self}")


class WeatherMetric(StrEnum):
    HIGH_TEMP = "high_temp"
    LOW_TEMP = "low_temp"
    PRECIP_SUM = "precip_sum"


class ContractSide(StrEnum):
    YES = "yes"
    NO = "no"


class Location(BaseModel):
    name: str
    latitude: float
    longitude: float
    timezone: str = "auto"
    region: str | None = None
    country: str = "US"


class MarketSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    city: str
    event_date: date
    metric: WeatherMetric
    comparator: Comparator
    threshold: Decimal
    unit: str
    location: Location | None
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    notes: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def canonical_key(self) -> str:
        return (
            f"{self.city.lower()}:{self.event_date.isoformat()}:"
            f"{self.metric}:{self.comparator}:{self.threshold}:{self.unit.lower()}"
        )


class RawMarket(BaseModel):
    market_id: str
    slug: str | None = None
    title: str
    condition_id: str | None = None
    active: bool = True
    closed: bool = False
    enable_order_book: bool = False
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[Decimal] = Field(default_factory=list)
    clob_token_ids: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def token_for_outcome(self, outcome_name: str) -> str | None:
        for idx, outcome in enumerate(self.outcomes):
            if outcome.lower() == outcome_name.lower() and idx < len(self.clob_token_ids):
                return self.clob_token_ids[idx]
        return None


class BookLevel(BaseModel):
    price: Decimal
    size: Decimal


class OrderBook(BaseModel):
    token_id: str
    market: str | None = None
    outcome: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)
    min_order_size: Decimal | None = None
    tick_size: Decimal | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def best_bid(self) -> Decimal | None:
        if not self.bids:
            return None
        return max(level.price for level in self.bids)

    @computed_field
    @property
    def best_ask(self) -> Decimal | None:
        if not self.asks:
            return None
        return min(level.price for level in self.asks)

    @computed_field
    @property
    def spread(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


class ForecastSnapshot(BaseModel):
    market_id: str | None = None
    model: str
    source: str = "open-meteo"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    spec: MarketSpec
    values: list[Decimal]
    raw: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def probability_yes(self) -> Decimal:
        if not self.values:
            return Decimal("0")
        hits = sum(
            1 for value in self.values if self.spec.comparator.test(value, self.spec.threshold)
        )
        return Decimal(hits) / Decimal(len(self.values))


class Signal(BaseModel):
    market_id: str
    slug: str | None = None
    title: str
    side: ContractSide
    model_probability_yes: Decimal
    side_probability: Decimal
    price: Decimal
    edge: Decimal
    expected_return: Decimal
    kelly_fraction: Decimal
    suggested_stake_usd: Decimal
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    spec: MarketSpec


class PaperOrder(BaseModel):
    signal_id: int | None = None
    market_id: str
    title: str
    side: ContractSide
    price: Decimal
    quantity: Decimal
    stake_usd: Decimal
    status: str = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MarketSettlement(BaseModel):
    condition_id: str
    resolved_at: datetime | None = None
    winning_outcome: str
    winning_outcome_index: int
    winning_token_id: str | None = None
    resolution_status: str | None = None
    outcome_prices: list[Decimal]
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = Field(default_factory=dict)
