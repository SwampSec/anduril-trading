import pytest
from decimal import Decimal

from conftest import order_for
from engine.decision import DecisionEngine
from risk.guardrails import RiskEngine


@pytest.mark.unit
def test_max_orders_per_day_enforced(fake_broker):
    risk = RiskEngine(broker=fake_broker, max_orders_per_day=3)
    risk.arm()
    for _ in range(3):
        risk.submit(order_for("ACME", "BUY", qty=1, px=10))
    ok, _ = risk.pre_trade_check(order_for("ACME", "BUY", qty=1, px=10))
    assert ok is False


@pytest.mark.unit
def test_duplicate_client_ref_not_resubmitted(fake_broker):
    risk = RiskEngine(broker=fake_broker)
    risk.arm()
    risk.submit(order_for("ACME", "BUY", qty=1, px=10, ref="abc"))
    risk.submit(order_for("ACME", "BUY", qty=1, px=10, ref="abc"))
    assert len(fake_broker.placed) == 1


@pytest.mark.unit
def test_daily_loss_breaker_halts(fake_broker):
    risk = RiskEngine(broker=fake_broker, max_daily_loss=Decimal("500"))
    risk.record_realized_pnl(Decimal("-600"))
    ok, reason = risk.pre_trade_check(order_for("ACME", "BUY", qty=1, px=10))
    assert ok is False and "loss" in reason.lower()


@pytest.mark.unit
def test_kill_switch_blocks_orders_but_not_analysis(fake_broker, monkeypatch):
    monkeypatch.setenv("ANDURIL_KILL_SWITCH", "1")
    risk = RiskEngine(broker=fake_broker)
    ok, _ = risk.pre_trade_check(order_for("ACME", "BUY", qty=1, px=10))
    assert ok is False
    assert DecisionEngine(broker=fake_broker).decide("ACME") is not None
