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
