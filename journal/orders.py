from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


DEFAULT_ORDER_PATH = Path(
    os.environ.get("ANDURIL_ORDER_LOG", "logs/orders.jsonl")
)


class OrderJournal:
    """Append-only order and fill history for API-submitted trades."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_ORDER_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def load_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                records.append(json.loads(raw))
        return records

    def tail(
        self,
        limit: int = 100,
        *,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self.load_all()
        if symbol:
            sym = symbol.upper()
            records = [r for r in records if r.get("symbol", "").upper() == sym]
        return records[-limit:]

    def known_exec_ids(self) -> set[str]:
        return {
            str(r["exec_id"])
            for r in self.load_all()
            if r.get("exec_id") not in (None, "")
        }

    def sync_executions(self, executions: list[dict[str, Any]]) -> int:
        known = self.known_exec_ids()
        added = 0
        for execution in executions:
            exec_id = str(execution.get("exec_id", ""))
            if not exec_id or exec_id in known:
                continue
            self.record("fill", {**execution, "source": "ibkr_sync"})
            known.add(exec_id)
            added += 1
        return added

    def summary(self) -> list[dict[str, Any]]:
        """Per-symbol net shares and average cost from recorded fills."""
        lots: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)

        for record in self.load_all():
            if record.get("event") not in {"fill", "order"}:
                continue
            shares = _decimal(record.get("filled_qty") or record.get("shares"))
            price = _decimal(record.get("fill_price") or record.get("avg_fill_price") or record.get("price"))
            if shares <= 0 or price <= 0:
                continue
            symbol = str(record.get("symbol", "")).upper()
            side = str(record.get("side", "")).upper()
            signed = shares if side == "BUY" else -shares
            lots[symbol].append((signed, price))

        summary: list[dict[str, Any]] = []
        for symbol in sorted(lots):
            net = Decimal("0")
            cost_basis = Decimal("0")
            for qty, price in lots[symbol]:
                if qty > 0:
                    cost_basis += qty * price
                    net += qty
                elif qty < 0:
                    if net > 0:
                        avg = cost_basis / net
                        sold = min(-qty, net)
                        cost_basis -= sold * avg
                        net -= sold
            avg_cost = (cost_basis / net) if net > 0 else None
            summary.append(
                {
                    "symbol": symbol,
                    "net_shares": str(net),
                    "avg_cost": str(avg_cost.quantize(Decimal("0.01"))) if avg_cost else None,
                }
            )
        return summary


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))
