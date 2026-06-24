from broker.config import IBKRConfig
from broker.logging_utils import log_account_status, mask_account_id
from broker.order import TradeOrder, account_mode

__all__ = [
    "IBKRConfig",
    "TradeOrder",
    "account_mode",
    "log_account_status",
    "mask_account_id",
]


def __getattr__(name: str):
    if name in {
        "IBAPI_AVAILABLE",
        "IBKRClient",
        "IBKRReadOnlyError",
        "IBKRRequestError",
    }:
        from broker import ibkr_client

        return getattr(ibkr_client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
