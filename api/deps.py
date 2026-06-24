from __future__ import annotations

from functools import lru_cache

from api.services.bot import BotService
from audit.logger import AuditLogger
from broker.config import IBKRConfig
from broker.ibkr_client import IBKRClient
from config.settings import AppSettings, get_settings
from llm.client import LMStudioClient
from journal.orders import OrderJournal
from risk.guardrails import RiskEngine


@lru_cache
def get_broker() -> IBKRClient:
    return IBKRClient(IBKRConfig.from_env())


@lru_cache
def get_risk() -> RiskEngine:
    return RiskEngine(get_broker())


@lru_cache
def get_llm() -> LMStudioClient:
    return LMStudioClient(get_settings())


@lru_cache
def get_audit_logger() -> AuditLogger:
    return AuditLogger()


@lru_cache
def get_order_journal() -> OrderJournal:
    return OrderJournal()


@lru_cache
def get_bot_service() -> BotService:
    return BotService(
        get_settings(),
        get_broker(),
        get_risk(),
        get_llm(),
        get_audit_logger(),
        get_order_journal(),
    )
