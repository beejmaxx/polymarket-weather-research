from __future__ import annotations

from pwmk.db.repository import Repository, init_db
from pwmk.parsing.normalize import normalize_market


def test_repository_saves_and_lists_markets(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"
    init_db(db_path)
    repo = Repository(db_path)
    bundle = normalize_market(
        {
            "id": "123",
            "question": "Will it rain tomorrow?",
            "conditionId": "0xabc",
            "slug": "will-it-rain",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.33", "0.67"]',
            "clobTokenIds": '["111", "222"]',
            "volume24hr": 12.5,
            "volumeNum": "100.25",
            "liquidityNum": "5",
            "active": True,
            "closed": False,
        },
        observed_at="2026-05-02T12:00:00Z",
    )

    repo.save_market_bundle([bundle])

    markets = repo.list_markets()
    assert len(markets) == 1
    assert markets[0]["condition_id"] == "0xabc"
    assert markets[0]["volume_24h"] == 12.5
    assert repo.get_market("0xabc")["tokens"][1]["outcome"] == "No"
    assert repo.summary()["active_markets"] == 1


def test_repository_saves_events_outcomes_and_aggregates(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"
    init_db(db_path)
    repo = Repository(db_path)
    raw = {
        "id": "123",
        "question": "Will Bitcoin hit $150k?",
        "conditionId": "0xabc",
        "slug": "will-bitcoin-hit-150k",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.40", "0.60"]',
        "clobTokenIds": '["111", "222"]',
        "volume24hr": 20,
        "volumeNum": "100",
        "liquidityNum": "5",
        "active": True,
        "closed": False,
        "events": [{"id": "9", "slug": "bitcoin", "title": "Bitcoin"}],
    }
    repo.save_market_bundle([normalize_market(raw, observed_at="2026-05-02T12:00:00Z")])

    raw["volume24hr"] = 50
    raw["volumeNum"] = "180"
    repo.save_market_bundle([normalize_market(raw, observed_at="2026-05-02T12:30:00Z")])

    assert repo.list_events()[0]["event_id"] == "9"
    assert repo.get_market("0xabc")["tokens"][0]["outcome_price"] == 0.4
    assert repo.refresh_volume_aggregates(bucket_size="hour") == 1

    aggregates = repo.aggregate_series("0xabc", bucket_size="hour", hours=24)
    assert aggregates[0]["volume_total_delta"] == 80

    momentum = repo.volume_momentum(limit=5)
    assert momentum[0]["volume_24h_change"] == 30
