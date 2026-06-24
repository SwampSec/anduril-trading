from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    as_of: datetime

    def trade_price(self) -> Decimal | None:
        if self.last is not None and self.last > 0:
            return self.last
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / Decimal("2")
        if self.bid is not None and self.bid > 0:
            return self.bid
        if self.ask is not None and self.ask > 0:
            return self.ask
        return None
