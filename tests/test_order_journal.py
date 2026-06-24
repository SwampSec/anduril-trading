import pytest
from decimal import Decimal

from journal.orders import OrderJournal


@pytest.mark.unit
def test_order_journal_records_and_tails(tmp_path):
    journal = OrderJournal(tmp_path / "orders.jsonl")
    journal.record(
        "order",
        {
            "symbol": "SPY",
            "side": "BUY",
            "quantity": "1",
            "limit_price": "734.50",
            "status": "Filled",
            "order_id": 3,
        },
    )
    rows = journal.tail(10)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "SPY"


@pytest.mark.unit
def test_order_journal_sync_dedupes_exec_ids(tmp_path):
    journal = OrderJournal(tmp_path / "orders.jsonl")
    executions = [
        {
            "exec_id": "abc123",
            "symbol": "SPY",
            "side": "BUY",
            "shares": "1",
            "price": "734.10",
        }
    ]
    assert journal.sync_executions(executions) == 1
    assert journal.sync_executions(executions) == 0


@pytest.mark.unit
def test_order_journal_summary_avg_cost(tmp_path):
    journal = OrderJournal(tmp_path / "orders.jsonl")
    journal.record(
        "fill",
        {
            "symbol": "SPY",
            "side": "BUY",
            "shares": "2",
            "filled_qty": "2",
            "fill_price": "100",
        },
    )
    journal.record(
        "fill",
        {
            "symbol": "SPY",
            "side": "BUY",
            "shares": "2",
            "filled_qty": "2",
            "fill_price": "200",
        },
    )
    summary = journal.summary()
    assert len(summary) == 1
    assert summary[0]["symbol"] == "SPY"
    assert Decimal(summary[0]["net_shares"]) == Decimal("4")
    assert Decimal(summary[0]["avg_cost"]) == Decimal("150.00")
