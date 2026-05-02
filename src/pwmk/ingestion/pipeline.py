from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from pwmk.clients.polymarket import PolymarketClient, stream_market_events
from pwmk.db.repository import Repository, init_db
from pwmk.parsing.normalize import normalize_market, normalize_trade_event, utc_now_iso


@dataclass(frozen=True)
class PollResult:
    markets_seen: int
    snapshots_seen: int
    tokens_seen: int
    event_volume_rows: int
    observed_at: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StreamResult:
    assets_subscribed: int
    trades_seen: int
    seconds: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


async def poll_once(
    db_path: str | Path,
    *,
    limit: int = 100,
    page_size: int = 250,
    live_events: int = 25,
    include_live_volume: bool = True,
) -> PollResult:
    init_db(db_path)
    observed_at = utc_now_iso()
    repo = Repository(db_path)
    run_id = repo.start_run("poll")
    try:
        client = PolymarketClient()
        raw_markets = await client.fetch_markets(max_markets=limit, page_size=page_size)
        bundles = []
        for raw_market in raw_markets:
            try:
                bundles.append(normalize_market(raw_market, observed_at=observed_at))
            except ValueError:
                continue

        market_count, snapshot_count, token_count = repo.save_market_bundle(bundles)

        event_volume_rows = 0
        if include_live_volume and live_events > 0:
            event_ids: list[str] = []
            for bundle in bundles:
                event_id = bundle["market"].get("event_id")
                if event_id and event_id not in event_ids:
                    event_ids.append(str(event_id))
                if len(event_ids) >= live_events:
                    break

            for event_id in event_ids:
                payload = await client.fetch_live_volume(event_id)
                event_volume_rows += repo.save_event_volume(event_id, payload, observed_at)

        repo.finish_run(
            run_id,
            status="ok",
            markets_seen=market_count,
            snapshots_seen=snapshot_count + event_volume_rows,
        )
        return PollResult(
            markets_seen=market_count,
            snapshots_seen=snapshot_count,
            tokens_seen=token_count,
            event_volume_rows=event_volume_rows,
            observed_at=observed_at,
        )
    except Exception as exc:
        repo.finish_run(run_id, status="error", error=str(exc))
        raise


async def poll_loop(
    db_path: str | Path,
    *,
    limit: int = 100,
    interval: int = 60,
    live_events: int = 25,
) -> None:
    while True:
        result = await poll_once(db_path, limit=limit, live_events=live_events)
        print(result.as_dict(), flush=True)
        await asyncio.sleep(interval)


async def stream_trades(
    db_path: str | Path,
    *,
    asset_limit: int = 50,
    duration: int | None = None,
    bootstrap_limit: int = 100,
) -> StreamResult:
    init_db(db_path)
    repo = Repository(db_path)
    token_map = repo.list_token_map(limit=asset_limit)
    if not token_map:
        await poll_once(db_path, limit=bootstrap_limit, live_events=0)
        token_map = repo.list_token_map(limit=asset_limit)

    run_id = repo.start_run("stream")
    started = time.monotonic()
    trades_seen = 0
    events = stream_market_events(list(token_map.keys()))
    try:
        while True:
            if duration is None:
                event = await anext(events)
            else:
                remaining = duration - (time.monotonic() - started)
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(anext(events), timeout=remaining)
                except TimeoutError:
                    break

            trade = normalize_trade_event(event, token_map)
            if trade and repo.save_trade(trade):
                trades_seen += 1

        seconds = time.monotonic() - started
        repo.finish_run(run_id, status="ok", trades_seen=trades_seen)
        return StreamResult(
            assets_subscribed=len(token_map),
            trades_seen=trades_seen,
            seconds=round(seconds, 3),
        )
    except Exception as exc:
        repo.finish_run(run_id, status="error", trades_seen=trades_seen, error=str(exc))
        raise
    finally:
        await events.aclose()
