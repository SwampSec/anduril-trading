import pytest
from decimal import Decimal

from conftest import PAPER_MARGIN_SUMMARY, FakeBroker
from engine.decision import DecisionEngine
from risk.guardrails import RiskEngine


@pytest.mark.unit
def test_decision_respects_max_shares_cap():
    broker = FakeBroker(summary=PAPER_MARGIN_SUMMARY)
    risk = RiskEngine(broker=broker)
    engine = DecisionEngine(broker=broker, risk=risk, max_shares=3)
    decision = engine.decide("SPY", price=Decimal("100"))
    assert decision.action == "BUY"
    assert decision.quantity == 3
