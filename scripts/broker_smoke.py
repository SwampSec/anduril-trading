#!/usr/bin/env python3
"""Smoke test: connect to IB Gateway and print masked account summary."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from broker.config import IBKRConfig
from broker.ibkr_client import IBAPI_AVAILABLE, IBKRClient
from broker.logging_utils import log_account_status, mask_account_id


def main() -> None:
    if not IBAPI_AVAILABLE:
        raise SystemExit(
            "ibapi not installed. Run scripts/install_ibapi.sh first."
        )

    config = IBKRConfig.from_env()
    client = IBKRClient(config)
    client.connect()
    try:
        summary = client.get_account_summary()
        print(f"mode={client.mode} account={mask_account_id(summary['account_id'])}")
        print(f"SettledCash={summary['SettledCash']} TotalCashValue={summary['TotalCashValue']}")
        log_account_status(client)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
