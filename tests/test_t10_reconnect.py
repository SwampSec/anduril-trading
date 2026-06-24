import pytest

from conftest import order_for
from risk.guardrails import RiskEngine


@pytest.mark.unit
def test_no_orders_until_reconciled_after_disconnect(fake_broker):
    fake_broker.connected = False
    risk = RiskEngine(broker=fake_broker)
    risk.on_disconnect()
    ok, _ = risk.pre_trade_check(order_for("ACME", "BUY", qty=1, px=10))
    assert ok is False
    fake_broker.connected = True
    risk.reconcile()
    ok, _ = risk.pre_trade_check(order_for("ACME", "BUY", qty=1, px=10))
    assert ok is True
