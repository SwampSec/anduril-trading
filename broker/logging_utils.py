from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("anduril.broker")


def mask_account_id(account_id: str) -> str:
    if len(account_id) <= 4:
        return "••••"
    return f"{account_id[:4]}••{account_id[-2:]}"


def log_account_status(broker: Any) -> None:
    summary = broker.get_account_summary()
    account_id = str(summary.get("account_id", ""))
    logger.info("Account %s connected (mode=%s)", mask_account_id(account_id), broker.mode)
