import threading

import pytest
from decimal import Decimal

from conftest import order_for
from risk.guardrails import RiskEngine, TradingHalted


@pytest.mark.unit
def test_concurrent_buys_cannot_double_spend(fake_broker):
    risk = RiskEngine(broker=fake_broker)
    results = []
    barrier = threading.Barrier(2)

    def attempt():
        barrier.wait()
        ok = risk.reserve_and_check(order_for("ACME", "BUY", qty=100, px=100))
        results.append(ok)

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sum(1 for r in results if r) == 1
    assert risk.total_reserved() <= fake_broker.summary["SettledCash"]


@pytest.mark.unit
def test_ledger_divergence_halts_trading(fake_broker):
    risk = RiskEngine(broker=fake_broker)
    risk.record_reservation("ACME", Decimal("5000"))
    fake_broker.summary["TotalCashValue"] = Decimal("2000")
    with pytest.raises(TradingHalted):
        risk.reconcile()
