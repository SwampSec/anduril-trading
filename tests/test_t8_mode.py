import pytest

from conftest import FakeBroker, LIVE_MARGIN_SUMMARY, PAPER_MARGIN_SUMMARY
from engine.decision import DecisionEngine
from risk.guardrails import RefuseToArm, RiskEngine


@pytest.mark.unit
def test_mode_detected_from_account_prefix():
    assert FakeBroker(summary=dict(PAPER_MARGIN_SUMMARY)).mode == "paper"
    assert FakeBroker(summary=dict(LIVE_MARGIN_SUMMARY)).mode == "live"


@pytest.mark.unit
def test_live_requires_explicit_confirmation(monkeypatch):
    monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
    broker = FakeBroker(summary=dict(LIVE_MARGIN_SUMMARY))
    with pytest.raises(RefuseToArm):
        RiskEngine(broker=broker).arm()


@pytest.mark.unit
def test_mode_intent_mismatch_refuses_start(monkeypatch):
    monkeypatch.setenv("ANDURIL_INTENDED_MODE", "paper")
    broker = FakeBroker(summary=dict(LIVE_MARGIN_SUMMARY))
    with pytest.raises(RefuseToArm):
        RiskEngine(broker=broker).arm()


@pytest.mark.unit
def test_every_order_record_stamps_mode(fake_broker):
    decision = DecisionEngine(broker=fake_broker).decide("ACME")
    assert decision.mode in ("paper", "live")
