from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
DATA_BASE_URL = "https://data-api.polymarket.com"
MARKET_WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass(frozen=True)
class PolymarketClient:
    timeout: float = 20.0

    async def fetch_markets(
        self,
        *,
        max_markets: int = 100,
        page_size: int = 250,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        cursor: str | None = None
        page_size = max(1, min(page_size, 1000))

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while len(markets) < max_markets:
                params: dict[str, Any] = {
                    "limit": min(page_size, max_markets - len(markets)),
                    "closed": str(closed).lower(),
                    "order": order,
                    "ascending": str(ascending).lower(),
                }
                if cursor:
                    params["after_cursor"] = cursor

                response = await client.get(f"{GAMMA_BASE_URL}/markets/keyset", params=params)
                response.raise_for_status()
                payload = response.json()
                page = payload.get("markets", [])
                if not isinstance(page, list):
                    raise ValueError("Unexpected Gamma markets response: missing markets list")

                markets.extend(page)
                cursor = payload.get("next_cursor")
                if not cursor or not page:
                    break

        return markets

    async def fetch_live_volume(self, event_id: str | int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{DATA_BASE_URL}/live-volume", params={"id": event_id})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Unexpected live-volume response: expected a list")
            return payload


async def _heartbeat(websocket: websockets.WebSocketClientProtocol) -> None:
    while True:
        await asyncio.sleep(10)
        await websocket.send("PING")


async def stream_market_events(asset_ids: Sequence[str]) -> AsyncIterator[dict[str, Any]]:
    if not asset_ids:
        return

    subscription = {
        "assets_ids": list(asset_ids),
        "type": "market",
        "custom_feature_enabled": True,
    }

    async with websockets.connect(MARKET_WSS_URL, ping_interval=None) as websocket:
        await websocket.send(json.dumps(subscription))
        heartbeat_task = asyncio.create_task(_heartbeat(websocket))
        try:
            while True:
                message = await websocket.recv()
                if message in {"PONG", "pong"}:
                    continue
                payload = json.loads(message)
                if isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict):
                            yield item
                elif isinstance(payload, dict):
                    yield payload
        finally:
            heartbeat_task.cancel()
