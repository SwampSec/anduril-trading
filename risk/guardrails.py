from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol


CASH_TAGS = ("SettledCash", "TotalCashValue")


class TradingHalted(Exception):
    """Raised when internal ledger diverges from broker-reported cash."""


class RefuseToArm(Exception):
    """Raised when live/mode gates block arming the trading engine."""


@dataclass(frozen=True)
class Quote:
    price: Decimal
    ts: datetime


class BrokerProtocol(Protocol):
    connected: bool
    mode: str

    def get_account_summary(self) -> dict[str, Any]: ...
    def get_positions(self) -> dict[str, Decimal]: ...
    def what_if(self, order: Any) -> dict[str, Any]: ...
    def place_order(self, order: Any) -> dict[str, Any]: ...


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _sizing_cash(summary: dict[str, Any]) -> Decimal:
    settled = _decimal(summary.get(CASH_TAGS[0], "0"))
    total = _decimal(summary.get(CASH_TAGS[1], "0"))
    return min(settled, total)


def _order_notional(order: Any) -> Decimal:
    price = order.limit_price if order.limit_price is not None else Decimal("0")
    return _decimal(order.quantity) * _decimal(price)


class RiskEngine:
    def __init__(
        self,
        broker: BrokerProtocol,
        *,
        max_orders_per_day: int = 50,
        max_daily_loss: Decimal | None = None,
        max_quote_age_s: int = 60,
        ledger_tolerance: Decimal = Decimal("0.01"),
    ) -> None:
        self.broker = broker
        self.max_orders_per_day = max_orders_per_day
        self.max_daily_loss = max_daily_loss
        self.max_quote_age_s = max_quote_age_s
        self.ledger_tolerance = ledger_tolerance

        self._armed = False
        self._halted = False
        self._needs_reconcile = False
        self._lock = threading.Lock()
        self._total_reserved = Decimal("0")
        self._reservations: dict[str, Decimal] = {}
        self._orders_today = 0
        self._submitted_refs: set[str] = set()
        self._realized_pnl = Decimal("0")

    @property
    def is_armed(self) -> bool:
        return self._armed and not self._halted

    def _intended_mode(self) -> str:
        return os.environ.get("ANDURIL_INTENDED_MODE", self.broker.mode)

    def _kill_switch_active(self) -> bool:
        return os.environ.get("ANDURIL_KILL_SWITCH") == "1"

    def available_cash(self) -> Decimal:
        summary = self.broker.get_account_summary()
        return _sizing_cash(summary)

    def total_reserved(self) -> Decimal:
        return self._total_reserved

    def max_buy_quantity(self, symbol: str, price: Decimal) -> int:
        if price <= 0:
            return 0
        spendable = self.available_cash() - self._total_reserved
        if spendable <= 0:
            return 0
        return int(spendable // price)

    def record_reservation(self, symbol: str, amount: Decimal) -> None:
        with self._lock:
            self._total_reserved += amount
            self._reservations[symbol] = self._reservations.get(symbol, Decimal("0")) + amount

    def record_realized_pnl(self, amount: Decimal) -> None:
        self._realized_pnl += amount

    def on_disconnect(self) -> None:
        self._needs_reconcile = True

    def arm(self) -> None:
        detected = self.broker.mode
        intended = self._intended_mode()
        if detected != intended:
            raise RefuseToArm(
                f"mode mismatch: detected={detected}, intended={intended}"
            )
        if detected == "live" and os.environ.get("LIVE_TRADING_CONFIRMED") != "1":
            raise RefuseToArm("live trading requires LIVE_TRADING_CONFIRMED=1")
        self._armed = True

    def reconcile(self) -> None:
        if not self.broker.connected:
            raise TradingHalted("cannot reconcile while disconnected")

        summary = self.broker.get_account_summary()
        broker_cash = _sizing_cash(summary)
        if self._total_reserved > broker_cash + self.ledger_tolerance:
            self._halted = True
            raise TradingHalted(
                "ledger divergence: reserved cash exceeds broker-reported cash"
            )
        self._needs_reconcile = False

    def pre_trade_check(self, order: Any, quote: Quote | None = None) -> tuple[bool, str]:
        if self._kill_switch_active():
            return False, "kill switch active"

        if self.max_daily_loss is not None and self._realized_pnl <= -self.max_daily_loss:
            return False, "daily loss limit reached"

        if self._halted:
            return False, "trading halted"

        if not self.broker.connected:
            return False, "broker disconnected"

        if self._needs_reconcile:
            return False, "reconciliation required"

        if quote is not None:
            age = (datetime.now(timezone.utc) - quote.ts).total_seconds()
            if age > self.max_quote_age_s:
                return False, "stale quote"

        if self._orders_today >= self.max_orders_per_day:
            return False, "max orders per day reached"

        try:
            summary = self.broker.get_account_summary()
            positions = self.broker.get_positions()
        except Exception as exc:
            return False, f"data unavailable: {exc}"

        side = str(order.side).upper()
        qty = _decimal(order.quantity)

        if side == "SELL":
            held = _decimal(positions.get(order.symbol, Decimal("0")))
            if qty > held:
                return False, "sell quantity exceeds shares held"
            return True, "ok"

        if side == "BUY":
            impact = self.broker.what_if(order)
            init_margin = _decimal(impact.get("init_margin_req", "0"))
            if init_margin > 0:
                return False, "order would require margin"

            notional = _order_notional(order)
            spendable = _sizing_cash(summary) - self._total_reserved
            if notional > spendable:
                return False, "insufficient cash"

            return True, "ok"

        return False, f"unsupported side: {side}"

    def reserve_and_check(self, order: Any) -> bool:
        with self._lock:
            ok, _ = self.pre_trade_check(order)
            if not ok:
                return False

            if str(order.side).upper() != "BUY":
                return True

            notional = _order_notional(order)
            spendable = self.available_cash() - self._total_reserved
            if notional > spendable:
                return False

            self._total_reserved += notional
            self._reservations[order.symbol] = (
                self._reservations.get(order.symbol, Decimal("0")) + notional
            )
            return True

    def submit(self, order: Any) -> dict[str, Any] | None:
        if not self.is_armed:
            return None

        if order.client_ref and order.client_ref in self._submitted_refs:
            return None

        ok, reason = self.pre_trade_check(order)
        if not ok:
            raise ValueError(reason)

        result = self.broker.place_order(order)
        if order.client_ref:
            self._submitted_refs.add(order.client_ref)
        self._orders_today += 1
        return result
