import pytest

from broker.ibkr_client import IBAPI_AVAILABLE


@pytest.mark.paper
def test_real_whatif_reports_margin_for_oversized_order():
    if not IBAPI_AVAILABLE:
        pytest.skip("official ibapi not installed")
    from decimal import Decimal

    from broker.config import IBKRConfig
    from broker.ibkr_client import IBKRClient
    from broker.order import TradeOrder

    client = IBKRClient(IBKRConfig(port=4002, read_only=True))
    client.connect()
    try:
        assert client.mode == "paper"
        impact = client.what_if(
            TradeOrder(
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("100000"),
                order_type="LMT",
                limit_price=Decimal("200"),
            )
        )
        assert impact["init_margin_req"] >= 0
    finally:
        client.disconnect()


@pytest.mark.paper
def test_real_oversell_rejected_by_gateway():
    pytest.skip("Wire manual oversell attempt against paper Gateway")
