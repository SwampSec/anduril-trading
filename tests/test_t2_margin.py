import pathlib

import pytest
from decimal import Decimal

from conftest import order_for
from risk.guardrails import RiskEngine

FORBIDDEN_SIZING_FIELDS = {"BuyingPower", "AvailableFunds"}
SIZING_SOURCES = ["risk/guardrails.py"]


@pytest.mark.unit
@pytest.mark.parametrize("src", SIZING_SOURCES)
def test_sizing_path_never_references_buying_power(src):
    path = pathlib.Path(src)
    if not path.exists():
        pytest.skip(f"{src} not built yet")
    source = path.read_text()
    for field in FORBIDDEN_SIZING_FIELDS:
        assert field not in source, (
            f"{src} references {field!r}; sizing MUST use TotalCashValue/SettledCash"
        )


@pytest.mark.unit
def test_buy_notional_never_exceeds_settled_cash(fake_broker):
    risk = RiskEngine(broker=fake_broker)
    qty = risk.max_buy_quantity(symbol="ACME", price=Decimal("100"))
    notional = qty * Decimal("100")
    assert notional <= fake_broker.summary["SettledCash"]


@pytest.mark.unit
def test_order_requiring_margin_is_rejected(fake_broker):
    fake_broker._whatif_init_margin["ACME"] = Decimal("5000")
    risk = RiskEngine(broker=fake_broker)
    ok, reason = risk.pre_trade_check(order_for("ACME", "BUY", qty=200, px=100))
    assert ok is False and "margin" in reason.lower()
    assert fake_broker.placed == []


@pytest.mark.unit
def test_cannot_sell_more_than_held(fake_broker):
    fake_broker.positions["ACME"] = Decimal("50")
    risk = RiskEngine(broker=fake_broker)
    ok, _ = risk.pre_trade_check(order_for("ACME", "SELL", qty=200, px=100))
    assert ok is False


@pytest.mark.unit
def test_sizing_uses_settled_not_total_when_unsettled(fake_broker):
    fake_broker.summary["SettledCash"] = Decimal("3000")
    fake_broker.summary["TotalCashValue"] = Decimal("10000")
    qty = RiskEngine(broker=fake_broker).max_buy_quantity("ACME", Decimal("100"))
    assert qty * Decimal("100") <= Decimal("3000")
