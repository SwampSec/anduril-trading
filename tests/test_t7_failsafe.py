from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from conftest import FakeBroker, order_for
from risk.guardrails import Quote, RiskEngine


@pytest.mark.unit
def test_data_fetch_exception_blocks_trade(fake_broker, monkeypatch):
    def boom(*_args, **_kwargs):
        raise TimeoutError("market data down")

    monkeypatch.setattr(fake_broker, "get_account_summary", boom)
    ok, _ = RiskEngine(broker=fake_broker).pre_trade_check(
        order_for("ACME", "BUY", qty=1, px=10)
    )
    assert ok is False


@pytest.mark.unit
def test_stale_data_blocks_trade(fake_broker):
    quote = Quote(
        price=Decimal("100"),
        ts=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    ok, _ = RiskEngine(broker=fake_broker, max_quote_age_s=60).pre_trade_check(
        order_for("ACME", "BUY", qty=1, px=100),
        quote=quote,
    )
    assert ok is False


@pytest.mark.unit
def test_default_state_is_not_trading():
    risk = RiskEngine(broker=FakeBroker())
    assert risk.is_armed is False
