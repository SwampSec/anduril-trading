import pytest
from decimal import Decimal

from broker.order import TradeOrder, account_mode


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
