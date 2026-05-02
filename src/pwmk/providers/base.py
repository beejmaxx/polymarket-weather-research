from __future__ import annotations

from typing import Any, Protocol


class MarketProvider(Protocol):
    name: str

    async def fetch_markets(self, *, limit: int) -> list[dict[str, Any]]:
        """Return provider-native market payloads for normalization."""

    async def fetch_live_volume(self, event_id: str) -> list[dict[str, Any]]:
        """Return provider-native live volume payloads for one event."""

