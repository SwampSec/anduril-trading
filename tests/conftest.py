import pytest
from dataclasses import dataclass
from decimal import Decimal

PAPER_MARGIN_SUMMARY = {
    "account_id": "DU1234567",
    "TotalCashValue": Decimal("10000.00"),
    "SettledCash": Decimal("10000.00"),
    "AvailableFunds": Decimal("40000.00"),
    "BuyingPower": Decimal("40000.00"),
    "NetLiquidation": Decimal("10000.00"),
}

LIVE_MARGIN_SUMMARY = dict(PAPER_MARGIN_SUMMARY, account_id="U7654321")


@dataclass
class FakeOrder:
    symbol: str
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None = None
    client_ref: str | None = None


class FakeBroker:
    def __init__(self, summary=None, positions=None, whatif_init_margin=None):
        self.summary = summary or dict(PAPER_MARGIN_SUMMARY)
        self.positions = positions or {}
        self.placed = []
        self.connected = True
        self._whatif_init_margin = whatif_init_margin or {}

    @property
    def mode(self):
        return "paper" if self.summary["account_id"].startswith("DU") else "live"

    def get_account_summary(self):
        return dict(self.summary)

    def get_positions(self):
        return dict(self.positions)

    def what_if(self, order: FakeOrder) -> dict:
        init_margin = self._whatif_init_margin.get(order.symbol, Decimal("0"))
        return {"init_margin_req": init_margin}

    def place_order(self, order: FakeOrder):
        if not self.connected:
            raise ConnectionError("Gateway disconnected")
        self.placed.append(order)
        return {
            "order_id": len(self.placed),
            "status": "PreSubmitted",
            "client_ref": order.client_ref,
        }


def order_for(symbol, side, qty, px, ref=None) -> FakeOrder:
    return FakeOrder(
        symbol=symbol,
        side=side,
        quantity=Decimal(str(qty)),
        order_type="LMT",
        limit_price=Decimal(str(px)),
        client_ref=ref,
    )


@pytest.fixture
def fake_broker():
    return FakeBroker()


@pytest.fixture(autouse=True)
def _never_live(monkeypatch):
    import os

    if os.environ.get("ANDURIL_TEST_ALLOW_LIVE") == "1":
        pytest.fail("Live trading must never be enabled inside the test suite.")


class FakeLLM:
    def __init__(self, response):
        self._response = response

    def complete(self, prompt: str) -> str:
        return self._response
