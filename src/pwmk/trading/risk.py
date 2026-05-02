from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskLimits:
    bankroll_usd: Decimal
    max_trade_usd: Decimal
    max_market_usd: Decimal
    fractional_kelly: Decimal = Decimal("0.25")

    def stake_for_kelly(self, kelly_fraction: Decimal) -> Decimal:
        if kelly_fraction <= 0:
            return Decimal("0")
        raw = self.bankroll_usd * kelly_fraction * self.fractional_kelly
        return min(raw, self.max_trade_usd, self.max_market_usd).quantize(Decimal("0.01"))
