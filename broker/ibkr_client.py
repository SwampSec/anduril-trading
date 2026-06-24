from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from broker.config import IBKRConfig
from broker.order import TradeOrder, account_mode
from broker.quotes import QuoteSnapshot

try:
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.order import Order
    from ibapi.wrapper import EWrapper

    IBAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when ibapi not installed
    IBAPI_AVAILABLE = False

    class EWrapper:  # type: ignore[no-redef]
        pass

    class EClient:  # type: ignore[no-redef]
        pass

    class Contract:  # type: ignore[no-redef]
        pass

    class Order:  # type: ignore[no-redef]
        pass

ACCOUNT_SUMMARY_TAGS = ("TotalCashValue", "SettledCash", "NetLiquidation")
INFO_ERROR_CODES = {2104, 2106, 2107, 2158, 2119, 2174, 10089, 10167}
TICK_BID = 1
TICK_ASK = 2
TICK_LAST = 4
TICK_CLOSE = 9


class IBKRRequestError(RuntimeError):
    pass


class IBKRReadOnlyError(RuntimeError):
    pass


def _require_ibapi() -> None:
    if not IBAPI_AVAILABLE:
        raise ImportError(
            "Official ibapi is not installed. Run scripts/install_ibapi.sh "
            "using source/pythonclient from https://interactivebrokers.github.io/"
        )


def _stock_contract(symbol: str) -> Contract:
    contract = Contract()
    contract.symbol = symbol.upper()
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    return contract


def _to_ib_order(trade: TradeOrder, *, what_if: bool) -> Order:
    order = Order()
    order.action = trade.side.upper()
    order.totalQuantity = float(trade.quantity)
    order.orderType = trade.order_type.upper()
    order.tif = "DAY"
    order.whatIf = what_if
    if trade.client_ref:
        order.orderRef = trade.client_ref
    if trade.order_type.upper() == "LMT":
        if trade.limit_price is None:
            raise ValueError("limit_price required for LMT orders")
        order.lmtPrice = float(trade.limit_price)
    return order


class _IBKRSession(EWrapper, EClient):
    def __init__(self, config: IBKRConfig) -> None:
        _require_ibapi()
        EClient.__init__(self, self)
        self.config = config
        self.connected_event = threading.Event()
        self.summary_event = threading.Event()
        self.positions_event = threading.Event()
        self.whatif_event = threading.Event()
        self.order_event = threading.Event()
        self.quote_event = threading.Event()
        self.error_event = threading.Event()

        self.next_order_id: int | None = None
        self.managed_accounts: list[str] = []
        self.account_id = ""
        self.summary: dict[str, Decimal] = {}
        self.positions: dict[str, Decimal] = {}
        self.quote_symbol = ""
        self.quote_bid: Decimal | None = None
        self.quote_ask: Decimal | None = None
        self.quote_last: Decimal | None = None
        self.hist_event = threading.Event()
        self.hist_close: Decimal | None = None
        self.last_error: tuple[int, str] | None = None
        self.whatif_init_margin = Decimal("0")
        self.last_order_status = ""
        self.last_order_id = 0

    def _record_summary_row(
        self, account: str, tag: str, value: str, currency: str
    ) -> None:
        if self.config.account and account != self.config.account:
            return
        if currency and currency not in {"USD", "BASE"}:
            return
        if tag in ACCOUNT_SUMMARY_TAGS:
            self.summary[tag] = Decimal(value)
        if not self.account_id:
            self.account_id = account

    def nextValidId(self, orderId: int) -> None:
        self.next_order_id = orderId
        self.connected_event.set()

    def managedAccounts(self, accountsList: str) -> None:
        self.managed_accounts = [a for a in accountsList.split(",") if a]
        if not self.account_id and self.managed_accounts:
            self.account_id = self.managed_accounts[0]

    def error(
        self,
        reqId: int,
        errorTime: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson="",
    ) -> None:
        if errorCode in INFO_ERROR_CODES:
            return
        self.last_error = (errorCode, errorString)
        if reqId in {-1, 0}:
            self.error_event.set()

    def connectionClosed(self) -> None:
        self.connected_event.clear()

    def accountSummary(
        self, reqId: int, account: str, tag: str, value: str, currency: str
    ) -> None:
        self._record_summary_row(account, tag, value, currency)

    def accountSummaryEnd(self, reqId: int) -> None:
        self.summary_event.set()

    def accountSummaryProtoBuf(self, accountSummaryProto) -> None:
        self._record_summary_row(
            accountSummaryProto.account,
            accountSummaryProto.tag,
            accountSummaryProto.value,
            accountSummaryProto.currency,
        )

    def accountSummaryEndProtoBuf(self, accountSummaryEndProto) -> None:
        self.summary_event.set()

    def position(self, account: str, contract: Contract, position: float, avgCost: float) -> None:
        if self.config.account and account != self.config.account:
            return
        if contract.secType != "STK":
            return
        symbol = contract.symbol.upper()
        qty = Decimal(str(position))
        if qty == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = qty

    def positionEnd(self) -> None:
        self.positions_event.set()

    def positionProtoBuf(self, positionProto) -> None:
        if self.config.account and positionProto.account != self.config.account:
            return
        if positionProto.contract.secType != "STK":
            return
        symbol = positionProto.contract.symbol.upper()
        qty = Decimal(str(positionProto.position))
        if qty == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = qty

    def positionEndProtoBuf(self, positionEndProto) -> None:
        self.positions_event.set()

    def _record_tick_price(self, tick_type: int, price: float) -> None:
        if price <= 0:
            return
        value = Decimal(str(price))
        if tick_type == TICK_BID:
            self.quote_bid = value
        elif tick_type == TICK_ASK:
            self.quote_ask = value
        elif tick_type in {TICK_LAST, TICK_CLOSE}:
            self.quote_last = value
        if self.quote_last is not None or (self.quote_bid is not None and self.quote_ask is not None):
            self.quote_event.set()

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib) -> None:
        self._record_tick_price(tickType, price)

    def tickPriceProtoBuf(self, tickPriceProto) -> None:
        self._record_tick_price(tickPriceProto.tickType, tickPriceProto.price)

    def tickSnapshotEnd(self, reqId: int) -> None:
        self.quote_event.set()

    def historicalData(self, reqId: int, bar) -> None:
        self.hist_close = Decimal(str(bar.close))

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        self.hist_event.set()

    def _record_whatif_margin(self, order_state) -> None:
        init_margin = getattr(order_state, "initMarginChange", "") or ""
        if init_margin not in ("", "0", "0.0"):
            try:
                self.whatif_init_margin = Decimal(str(init_margin))
            except Exception:
                self.whatif_init_margin = Decimal("0")

    def openOrder(self, orderId: int, contract: Contract, order: Order, orderState) -> None:
        self._record_whatif_margin(orderState)
        self.whatif_event.set()

    def openOrderEnd(self) -> None:
        self.whatif_event.set()

    def openOrderProtoBuf(self, openOrderProto) -> None:
        self._record_whatif_margin(openOrderProto.orderState)
        self.whatif_event.set()

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ) -> None:
        self.last_order_id = orderId
        self.last_order_status = status
        self.order_event.set()


class IBKRClient:
    """Official ibapi broker adapter implementing the RiskEngine broker protocol."""

    def __init__(self, config: IBKRConfig | None = None) -> None:
        self.config = config or IBKRConfig.from_env()
        self._session: _IBKRSession | None = None
        self._thread: threading.Thread | None = None
        self._order_id_counter = 0

    @property
    def connected(self) -> bool:
        return self._session is not None and self._session.isConnected()

    @property
    def mode(self) -> str:
        account_id = self._active_account_id()
        return account_mode(account_id)

    def connect(self) -> None:
        _require_ibapi()
        if self.connected:
            return

        session = _IBKRSession(self.config)
        session.connect(
            self.config.host,
            self.config.port,
            self.config.client_id,
        )
        self._thread = threading.Thread(target=session.run, daemon=True, name="ibkr-api")
        self._thread.start()

        if not session.connected_event.wait(self.config.connect_timeout_s):
            session.disconnect()
            raise IBKRRequestError("timed out waiting for IB Gateway connection")

        if session.config.account:
            session.account_id = session.config.account
        elif session.managed_accounts:
            session.account_id = session.managed_accounts[0]

        if not session.account_id:
            raise IBKRRequestError("no managed account returned by IB Gateway")

        # Prefer delayed quotes when live subscriptions are unavailable (paper API).
        session.reqMarketDataType(3)

        self._session = session

    def disconnect(self) -> None:
        if self._session is not None:
            self._session.disconnect()
            self._session = None
        self._thread = None

    def reconcile(self) -> None:
        self.get_account_summary()
        self.get_positions()

    def get_account_summary(self) -> dict[str, Any]:
        session = self._require_session()
        session.summary.clear()
        session.summary_event.clear()
        session.reqAccountSummary(9001, "All", ",".join(ACCOUNT_SUMMARY_TAGS))
        self._wait(session.summary_event, "account summary")
        session.cancelAccountSummary(9001)

        if not session.summary:
            raise IBKRRequestError("account summary empty")

        account_id = self._active_account_id()
        payload: dict[str, Any] = {"account_id": account_id}
        for tag in ACCOUNT_SUMMARY_TAGS:
            if tag not in session.summary:
                if tag == "SettledCash" and "TotalCashValue" in session.summary:
                    payload[tag] = session.summary["TotalCashValue"]
                    continue
                raise IBKRRequestError(f"missing account summary field: {tag}")
            payload[tag] = session.summary[tag]
        return payload

    def get_positions(self) -> dict[str, Decimal]:
        session = self._require_session()
        session.positions.clear()
        session.positions_event.clear()
        session.reqPositions()
        self._wait(session.positions_event, "positions")
        session.cancelPositions()
        return dict(session.positions)

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        session = self._require_session()
        req_id = 9101
        contract = _stock_contract(symbol)

        for snapshot in (True, False):
            session.quote_event.clear()
            session.quote_symbol = symbol.upper()
            session.quote_bid = None
            session.quote_ask = None
            session.quote_last = None
            session.reqMktData(req_id, contract, "", snapshot, False, [])
            try:
                self._wait(session.quote_event, "market data")
            except IBKRRequestError:
                session.cancelMktData(req_id)
                continue
            session.cancelMktData(req_id)
            if session.quote_last is not None or (
                session.quote_bid is not None and session.quote_ask is not None
            ):
                break

        snapshot_obj = QuoteSnapshot(
            symbol=session.quote_symbol,
            bid=session.quote_bid,
            ask=session.quote_ask,
            last=session.quote_last,
            as_of=datetime.now(timezone.utc),
        )
        if snapshot_obj.trade_price() is not None:
            return snapshot_obj

        return self._historical_close_quote(symbol)

    def _historical_close_quote(self, symbol: str) -> QuoteSnapshot:
        session = self._require_session()
        session.hist_event.clear()
        session.hist_close = None
        req_id = 9201
        contract = _stock_contract(symbol)
        session.reqHistoricalData(
            req_id,
            contract,
            "",
            "1 D",
            "1 day",
            "TRADES",
            1,
            1,
            False,
            [],
        )
        self._wait(session.hist_event, "historical close")
        session.cancelHistoricalData(req_id)
        if session.hist_close is None or session.hist_close <= 0:
            raise IBKRRequestError(f"no historical price for {symbol.upper()}")
        return QuoteSnapshot(
            symbol=symbol.upper(),
            bid=None,
            ask=None,
            last=session.hist_close,
            as_of=datetime.now(timezone.utc),
        )

    def get_trade_price(self, symbol: str) -> Decimal:
        quote = self.get_quote(symbol)
        price = quote.trade_price()
        if price is None or price <= 0:
            raise IBKRRequestError(f"no market price available for {symbol.upper()}")
        return price

    def what_if(self, order: TradeOrder) -> dict[str, Any]:
        session = self._require_session()
        session.whatif_init_margin = Decimal("0")
        session.whatif_event.clear()
        order_id = self._next_order_id()
        ib_order = _to_ib_order(order, what_if=True)
        session.placeOrder(order_id, _stock_contract(order.symbol), ib_order)
        self._wait(session.whatif_event, "what-if")
        return {"init_margin_req": session.whatif_init_margin}

    def place_order(self, order: TradeOrder) -> dict[str, Any]:
        if self.config.read_only:
            raise IBKRReadOnlyError(
                "IBKR client is read-only; disable IBKR_READ_ONLY only for armed trading"
            )

        session = self._require_session()
        session.order_event.clear()
        order_id = self._next_order_id()
        ib_order = _to_ib_order(order, what_if=False)
        session.placeOrder(order_id, _stock_contract(order.symbol), ib_order)
        self._wait(session.order_event, "order status")

        return {
            "order_id": session.last_order_id,
            "status": session.last_order_status,
            "client_ref": order.client_ref,
            "mode": self.mode,
        }

    def _active_account_id(self) -> str:
        session = self._require_session()
        account_id = session.account_id or (session.managed_accounts[0] if session.managed_accounts else "")
        if not account_id:
            raise IBKRRequestError("account id unavailable")
        return account_id

    def _require_session(self) -> _IBKRSession:
        if not self.connected or self._session is None:
            raise IBKRRequestError("not connected to IB Gateway")
        return self._session

    def _next_order_id(self) -> int:
        session = self._require_session()
        if session.next_order_id is None:
            raise IBKRRequestError("next valid order id unavailable")
        order_id = session.next_order_id + self._order_id_counter
        self._order_id_counter += 1
        return order_id

    def _wait(self, event: threading.Event, label: str) -> None:
        session = self._require_session()
        if not event.wait(self.config.request_timeout_s):
            raise IBKRRequestError(f"timed out waiting for {label}")
        if session.last_error and session.last_error[0] >= 1000:
            code, message = session.last_error
            raise IBKRRequestError(f"{label} failed ({code}): {message}")
