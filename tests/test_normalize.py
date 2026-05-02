from __future__ import annotations

from pwmk.parsing.normalize import normalize_market, normalize_trade_event, parse_json_array


def test_parse_json_array_handles_gamma_strings() -> None:
    assert parse_json_array('["Yes", "No"]') == ["Yes", "No"]
    assert parse_json_array('"[\\"Yes\\", \\"No\\"]"') == ["Yes", "No"]
    assert parse_json_array(None) == []


def test_normalize_market_maps_tokens_and_snapshot() -> None:
    raw = {
        "id": "123",
        "question": "Will it rain tomorrow?",
        "conditionId": "0xabc",
        "slug": "will-it-rain",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.33", "0.67"]',
        "clobTokenIds": '["111", "222"]',
        "volume24hr": 12.5,
        "volumeNum": "100.25",
        "active": True,
        "closed": False,
        "events": [{"id": "9", "slug": "weather", "title": "Weather"}],
    }

    bundle = normalize_market(raw, observed_at="2026-05-02T12:00:00Z")

    assert bundle["market"]["condition_id"] == "0xabc"
    assert bundle["market"]["event_id"] == "9"
    assert bundle["snapshot"]["volume_total"] == 100.25
    assert bundle["snapshot"]["volume_24h"] == 12.5
    assert bundle["tokens"][0]["token_id"] == "111"
    assert bundle["tokens"][0]["outcome"] == "Yes"
    assert bundle["tokens"][0]["outcome_price"] == 0.33


def test_normalize_trade_event_builds_notional() -> None:
    event = {
        "event_type": "last_trade_price",
        "asset_id": "111",
        "market": "0xabc",
        "price": "0.40",
        "size": "25",
        "side": "BUY",
        "timestamp": "1750428146322",
        "transaction_hash": "0xhash",
    }

    trade = normalize_trade_event(event, {"111": "0xabc"}, observed_at="2026-05-02T12:00:00Z")

    assert trade is not None
    assert trade["condition_id"] == "0xabc"
    assert trade["notional"] == 10.0
    assert trade["trade_key"]
