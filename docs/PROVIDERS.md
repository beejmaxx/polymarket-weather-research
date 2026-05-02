# Provider Extension Guide

The volume layer currently normalizes Polymarket payloads. Additional providers should implement `pwmk.providers.base.MarketProvider` and return provider-native payloads from:

- `fetch_markets(limit=...)`
- `fetch_live_volume(event_id=...)`

Then add a normalizer that maps provider payloads into the same internal concepts:

- event
- market
- outcome
- token or contract identifier
- snapshot
- trade

Keep raw payloads in snapshot/trade rows so upstream schema drift remains auditable.

