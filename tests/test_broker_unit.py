import pytest
from decimal import Decimal

from broker.order import TradeOrder, account_mode
from broker.quotes import QuoteSnapshot
from datetime import datetime, timezone


@pytest.mark.unit
def test_account_mode_paper():
    assert account_mode("DU1234567") == "paper"


@pytest.mark.unit
def test_account_mode_live():
    assert account_mode("U7654321") == "live"


@pytest.mark.unit
def test_account_mode_unknown_raises():
    with pytest.raises(ValueError):
        account_mode("X123")


@pytest.mark.unit
def test_trade_order_dataclass():
    order = TradeOrder(
        symbol="SPY",
        side="BUY",
        quantity=Decimal("1"),
        limit_price=Decimal("500"),
        client_ref="abc",
    )
    assert order.symbol == "SPY"
    assert order.client_ref == "abc"


@pytest.mark.unit
def test_quote_trade_price_prefers_last():
    quote = QuoteSnapshot(
        symbol="SPY",
        bid=Decimal("100"),
        ask=Decimal("102"),
        last=Decimal("101"),
        as_of=datetime.now(timezone.utc),
    )
    assert quote.trade_price() == Decimal("101")


@pytest.mark.unit
def test_quote_trade_price_mid_from_bid_ask():
    quote = QuoteSnapshot(
        symbol="SPY",
        bid=Decimal("100"),
        ask=Decimal("102"),
        last=None,
        as_of=datetime.now(timezone.utc),
    )
    assert quote.trade_price() == Decimal("101")
