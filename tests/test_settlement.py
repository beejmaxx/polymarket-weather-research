from __future__ import annotations

from datetime import date
from decimal import Decimal

from pwmk.db.repository import Repository, init_db
from pwmk.models.domain import (
    Comparator,
    ContractSide,
    Location,
    MarketSpec,
    PaperOrder,
    Signal,
    WeatherMetric,
)
from pwmk.trading.settlement import infer_market_settlement


def test_infer_market_settlement_from_decisive_outcome_prices() -> None:
    settlement = infer_market_settlement(
        {
            "conditionId": "0xabc",
            "closed": True,
            "closedTime": "2026-05-02 17:06:28+00",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0", "1"]',
            "clobTokenIds": '["111", "222"]',
            "umaResolutionStatus": "resolved",
        }
    )

    assert settlement is not None
    assert settlement.condition_id == "0xabc"
    assert settlement.winning_outcome == "No"
    assert settlement.winning_outcome_index == 1
    assert settlement.winning_token_id == "222"


def test_infer_market_settlement_skips_ambiguous_prices() -> None:
    settlement = infer_market_settlement(
        {
            "conditionId": "0xabc",
            "closed": True,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.5", "0.5"]',
        }
    )

    assert settlement is None


def test_repository_weather_calibration_report(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"
    init_db(db_path)
    repo = Repository(db_path)
    spec = MarketSpec(
        title="Will Austin hit 80F?",
        city="Austin",
        event_date=date(2026, 5, 8),
        metric=WeatherMetric.HIGH_TEMP,
        comparator=Comparator.AT_OR_ABOVE,
        threshold=Decimal("80"),
        unit="F",
        location=Location(name="Austin", latitude=30.2, longitude=-97.7),
        confidence=Decimal("1"),
    )
    signal = Signal(
        market_id="0xabc",
        title=spec.title,
        side=ContractSide.YES,
        model_probability_yes=Decimal("0.80"),
        side_probability=Decimal("0.80"),
        price=Decimal("0.50"),
        edge=Decimal("0.30"),
        expected_return=Decimal("0.60"),
        kelly_fraction=Decimal("0.60"),
        suggested_stake_usd=Decimal("10"),
        reason="test",
        spec=spec,
    )
    signal_id = repo.save_weather_signal(signal)
    repo.save_weather_paper_order(
        PaperOrder(
            signal_id=signal_id,
            market_id="0xabc",
            title=spec.title,
            side=ContractSide.YES,
            price=Decimal("0.50"),
            quantity=Decimal("20"),
            stake_usd=Decimal("10"),
        )
    )
    settlement = infer_market_settlement(
        {
            "conditionId": "0xabc",
            "closed": True,
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["1", "0"]',
        }
    )
    assert settlement is not None
    repo.save_market_settlement(settlement)

    report = repo.weather_calibration_report()

    assert report["settled_orders"] == 1
    assert report["wins"] == 1
    assert report["pnl_usd"] == 10
    assert report["brier_score"] == 0.04
