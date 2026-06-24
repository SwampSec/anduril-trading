import json

import pytest

from audit.logger import AuditLogger


@pytest.mark.unit
def test_audit_append_and_tail(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)

    record = logger.append(
        "analyze",
        {"symbol": "SPY", "action": "HOLD", "price_used": "500"},
    )
    assert record["event"] == "analyze"
    assert "ts" in record

    rows = logger.tail(10)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "SPY"


@pytest.mark.unit
def test_audit_integrity_check(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.append("arm", {"armed": True})

    raw = path.read_text(encoding="utf-8").strip()
    wrapper = json.loads(raw)
    wrapper["sha256"] = "deadbeef"
    path.write_text(json.dumps(wrapper) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity"):
        logger.tail(1)
