from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 7
    account: str = ""
    read_only: bool = True
    connect_timeout_s: float = 15.0
    request_timeout_s: float = 10.0

    @classmethod
    def from_env(cls) -> IBKRConfig:
        return cls(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "4002")),
            client_id=int(os.environ.get("IBKR_CLIENT_ID", "7")),
            account=os.environ.get("IBKR_ACCOUNT", "").strip(),
            read_only=os.environ.get("IBKR_READ_ONLY", "true").lower()
            in {"1", "true", "yes"},
            connect_timeout_s=float(os.environ.get("IBKR_CONNECT_TIMEOUT_S", "15")),
            request_timeout_s=float(os.environ.get("IBKR_REQUEST_TIMEOUT_S", "10")),
        )
