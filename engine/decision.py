from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from news.overlay import NewsSignal, OverlayAction
from risk.guardrails import RiskEngine


class BrokerProtocol(Protocol):
    mode: str

    def get_account_summary(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Decision:
    symbol: str
    action: str
    quantity: int
    mode: str


class DecisionEngine:
    """Quantitative decision path — Python owns sizing; news overlay may only reduce."""

    def __init__(
        self,
        broker: BrokerProtocol,
        risk: RiskEngine | None = None,
        *,
        base_conviction: float = 0.6,
    ) -> None:
        self.broker = broker
        self.risk = risk
        self.base_conviction = base_conviction

    def decide(
        self,
        symbol: str,
        *,
        news: NewsSignal | None = None,
        price: Decimal = Decimal("100"),
    ) -> Decision:
        mode = self.broker.mode

        if news is not None and news.action == OverlayAction.VETO:
            return Decision(symbol=symbol, action="HOLD", quantity=0, mode=mode)

        conviction = self.base_conviction
        if news is not None:
            overlay = max(0.0, news.sentiment) * news.materiality
            conviction = min(conviction, overlay)

        if self.risk is None or conviction <= 0:
            return Decision(symbol=symbol, action="HOLD", quantity=0, mode=mode)

        max_qty = self.risk.max_buy_quantity(symbol, price)
        qty = int(max_qty * conviction)
        if qty <= 0:
            return Decision(symbol=symbol, action="HOLD", quantity=0, mode=mode)

        return Decision(symbol=symbol, action="BUY", quantity=qty, mode=mode)
