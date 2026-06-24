from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TradeOrder:
    symbol: str
    side: str
    quantity: Decimal
    order_type: str = "LMT"
    limit_price: Decimal | None = None
    client_ref: str | None = None


def account_mode(account_id: str) -> str:
    if account_id.startswith("DU"):
        return "paper"
    if account_id.startswith("U"):
        return "live"
    raise ValueError(f"unknown account id prefix for mode detection: {account_id!r}")
