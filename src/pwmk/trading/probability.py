from __future__ import annotations

from decimal import Decimal

from pwmk.models.domain import ForecastSnapshot


def raw_ensemble_probability(snapshot: ForecastSnapshot) -> Decimal:
    return snapshot.probability_yes


def brier_score(probability: Decimal, outcome: bool) -> Decimal:
    observed = Decimal("1") if outcome else Decimal("0")
    return (probability - observed) ** 2


def expected_return_on_stake(probability: Decimal, price: Decimal) -> Decimal:
    if price <= 0:
        return Decimal("0")
    return (probability - price) / price


def kelly_fraction_binary(probability: Decimal, price: Decimal) -> Decimal:
    """Kelly fraction for a binary $1 payoff contract bought at price."""
    if price <= 0 or price >= 1:
        return Decimal("0")
    net_odds = (Decimal("1") - price) / price
    loss_probability = Decimal("1") - probability
    fraction = (net_odds * probability - loss_probability) / net_odds
    return max(Decimal("0"), fraction)
