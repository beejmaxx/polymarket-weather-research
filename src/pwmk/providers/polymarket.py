from __future__ import annotations

from typing import Any

from pwmk.clients.polymarket import PolymarketClient


class PolymarketMarketProvider:
    name = "polymarket"

    def __init__(self, client: PolymarketClient | None = None):
        self.client = client or PolymarketClient()

    async def fetch_markets(self, *, limit: int) -> list[dict[str, Any]]:
        return await self.client.fetch_markets(max_markets=limit)

    async def fetch_live_volume(self, event_id: str) -> list[dict[str, Any]]:
        return await self.client.fetch_live_volume(event_id)
