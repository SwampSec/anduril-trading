from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from broker.ibkr_client import IBKRClient, IBKRReadOnlyError
from broker.logging_utils import mask_account_id
from broker.order import TradeOrder
from config.settings import AppSettings
from engine.decision import Decision, DecisionEngine
from llm.client import LMStudioClient
from news.overlay import NewsSignal, parse_news_signal
from risk.guardrails import RefuseToArm, RiskEngine


@dataclass(frozen=True)
class BotStatus:
    enabled: bool
    armed: bool
    kill_switch: bool
    read_only: bool
    connected: bool
    mode: str | None
    symbols: list[str]


@dataclass(frozen=True)
class RunResult:
    decision: Decision
    news: NewsSignal | None
    submitted: bool
    order_result: dict[str, Any] | None
    message: str


class BotService:
    def __init__(
        self,
        settings: AppSettings,
        broker: IBKRClient,
        risk: RiskEngine,
        llm: LMStudioClient,
    ) -> None:
        self.settings = settings
        self.broker = broker
        self.risk = risk
        self.decision_engine = DecisionEngine(broker=broker, risk=risk)
        self.llm = llm

    def status(self) -> BotStatus:
        import os

        mode: str | None = None
        if self.broker.connected:
            try:
                mode = self.broker.mode
            except Exception:
                mode = None

        return BotStatus(
            enabled=self.settings.bot_enabled,
            armed=self.risk.is_armed,
            kill_switch=os.environ.get("ANDURIL_KILL_SWITCH") == "1",
            read_only=self.broker.config.read_only,
            connected=self.broker.connected,
            mode=mode,
            symbols=self.settings.symbol_list,
        )

    async def connect(self) -> None:
        await asyncio.to_thread(self.broker.connect)

    async def disconnect(self) -> None:
        await asyncio.to_thread(self.broker.disconnect)

    async def reconcile(self) -> None:
        await asyncio.to_thread(self.risk.reconcile)

    async def arm(self) -> None:
        await asyncio.to_thread(self.risk.arm)

    async def disarm(self) -> None:
        await asyncio.to_thread(self.risk.disarm)

    async def analyze(
        self,
        symbol: str,
        price: Decimal,
        headline: str | None = None,
    ) -> tuple[Decision, NewsSignal | None]:
        symbol = symbol.upper()
        if symbol not in self.settings.symbol_list:
            raise ValueError(f"symbol must be one of: {self.settings.symbol_list}")

        news: NewsSignal | None = None
        if headline:
            news = await asyncio.to_thread(
                parse_news_signal, headline, self.llm
            )

        decision = await asyncio.to_thread(
            self.decision_engine.decide,
            symbol,
            news=news,
            price=price,
        )
        return decision, news

    async def run_once(
        self,
        symbol: str,
        price: Decimal,
        headline: str | None = None,
    ) -> RunResult:
        if not self.settings.bot_enabled:
            raise ValueError("BOT_ENABLED is false")

        decision, news = await self.analyze(symbol, price, headline)

        if decision.action == "HOLD" or decision.quantity <= 0:
            return RunResult(
                decision=decision,
                news=news,
                submitted=False,
                order_result=None,
                message="hold — no order placed",
            )

        if not self.risk.is_armed:
            return RunResult(
                decision=decision,
                news=news,
                submitted=False,
                order_result=None,
                message="not armed — analysis only",
            )

        order = TradeOrder(
            symbol=decision.symbol,
            side=decision.action,
            quantity=Decimal(decision.quantity),
            order_type="LMT",
            limit_price=price,
            client_ref=f"anduril-{decision.symbol}-{decision.mode}",
        )

        try:
            result = await asyncio.to_thread(self.risk.submit, order)
        except IBKRReadOnlyError:
            return RunResult(
                decision=decision,
                news=news,
                submitted=False,
                order_result=None,
                message="broker read-only — order blocked",
            )
        except RefuseToArm:
            return RunResult(
                decision=decision,
                news=news,
                submitted=False,
                order_result=None,
                message="risk engine refused to arm",
            )
        except ValueError as exc:
            return RunResult(
                decision=decision,
                news=news,
                submitted=False,
                order_result=None,
                message=str(exc),
            )

        return RunResult(
            decision=decision,
            news=news,
            submitted=result is not None,
            order_result=result,
            message="order submitted" if result else "duplicate or blocked",
        )

    async def account_summary_masked(self) -> dict[str, Any]:
        summary = await asyncio.to_thread(self.broker.get_account_summary)
        summary["account_id"] = mask_account_id(str(summary.get("account_id", "")))
        return summary
