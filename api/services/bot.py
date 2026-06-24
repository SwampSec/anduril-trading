from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from audit.logger import AuditLogger
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
    loop_running: bool
    kill_switch: bool
    read_only: bool
    connected: bool
    mode: str | None
    symbols: list[str]


@dataclass(frozen=True)
class RunResult:
    decision: Decision
    news: NewsSignal | None
    price_used: Decimal
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
        audit: AuditLogger | None = None,
    ) -> None:
        self.settings = settings
        self.broker = broker
        self.risk = risk
        self.decision_engine = DecisionEngine(broker=broker, risk=risk)
        self.llm = llm
        self.audit = audit or AuditLogger()
        self._loop_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_error: str | None = None

    @property
    def loop_running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

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
            loop_running=self.loop_running,
            kill_switch=os.environ.get("ANDURIL_KILL_SWITCH") == "1",
            read_only=self.broker.config.read_only,
            connected=self.broker.connected,
            mode=mode,
            symbols=self.settings.symbol_list,
        )

    async def connect(self) -> None:
        await asyncio.to_thread(self.broker.connect)

    async def disconnect(self) -> None:
        await self.stop_loop()
        await asyncio.to_thread(self.broker.disconnect)

    async def reconcile(self) -> None:
        await asyncio.to_thread(self.risk.reconcile)

    async def arm(self) -> None:
        await asyncio.to_thread(self.risk.arm)
        await self._log_event("arm", {"armed": True})

    async def disarm(self) -> None:
        await self.stop_loop()
        await asyncio.to_thread(self.risk.disarm)
        await self._log_event("disarm", {"armed": False})

    async def resolve_price(self, symbol: str, price: Decimal | None) -> Decimal:
        if price is not None:
            return price
        if not self.broker.connected:
            raise ValueError("broker not connected — pass price= or POST /ibkr/connect")
        return await asyncio.to_thread(self.broker.get_trade_price, symbol)

    async def analyze(
        self,
        symbol: str,
        price: Decimal | None = None,
        headline: str | None = None,
    ) -> tuple[Decision, NewsSignal | None, Decimal]:
        symbol = symbol.upper()
        if symbol not in self.settings.symbol_list:
            raise ValueError(f"symbol must be one of: {self.settings.symbol_list}")

        resolved_price = await self.resolve_price(symbol, price)

        news: NewsSignal | None = None
        if headline:
            news = await asyncio.to_thread(parse_news_signal, headline, self.llm)

        decision = await asyncio.to_thread(
            self.decision_engine.decide,
            symbol,
            news=news,
            price=resolved_price,
        )
        await self._log_event(
            "analyze",
            self._decision_payload(decision, news, resolved_price, headline),
        )
        return decision, news, resolved_price

    async def run_once(
        self,
        symbol: str,
        price: Decimal | None = None,
        headline: str | None = None,
    ) -> RunResult:
        if not self.settings.bot_enabled:
            raise ValueError("BOT_ENABLED is false")

        decision, news, resolved_price = await self.analyze(symbol, price, headline)

        if decision.action == "HOLD" or decision.quantity <= 0:
            result = RunResult(
                decision=decision,
                news=news,
                price_used=resolved_price,
                submitted=False,
                order_result=None,
                message="hold — no order placed",
            )
            await self._log_run_once(result, headline)
            return result

        if not self.risk.is_armed:
            result = RunResult(
                decision=decision,
                news=news,
                price_used=resolved_price,
                submitted=False,
                order_result=None,
                message="not armed — analysis only",
            )
            await self._log_run_once(result, headline)
            return result

        order = TradeOrder(
            symbol=decision.symbol,
            side=decision.action,
            quantity=Decimal(decision.quantity),
            order_type="LMT",
            limit_price=resolved_price,
            client_ref=f"anduril-{decision.symbol}-{decision.mode}",
        )

        try:
            order_result = await asyncio.to_thread(self.risk.submit, order)
        except IBKRReadOnlyError:
            result = RunResult(
                decision=decision,
                news=news,
                price_used=resolved_price,
                submitted=False,
                order_result=None,
                message="broker read-only — order blocked",
            )
            await self._log_run_once(result, headline)
            return result
        except RefuseToArm:
            result = RunResult(
                decision=decision,
                news=news,
                price_used=resolved_price,
                submitted=False,
                order_result=None,
                message="risk engine refused to arm",
            )
            await self._log_run_once(result, headline)
            return result
        except ValueError as exc:
            result = RunResult(
                decision=decision,
                news=news,
                price_used=resolved_price,
                submitted=False,
                order_result=None,
                message=str(exc),
            )
            await self._log_run_once(result, headline)
            return result

        result = RunResult(
            decision=decision,
            news=news,
            price_used=resolved_price,
            submitted=order_result is not None,
            order_result=order_result,
            message="order submitted" if order_result else "duplicate or blocked",
        )
        await self._log_run_once(result, headline)
        return result

    def _decision_payload(
        self,
        decision: Decision,
        news: NewsSignal | None,
        price_used: Decimal,
        headline: str | None,
    ) -> dict[str, Any]:
        return {
            "mode": decision.mode,
            "symbol": decision.symbol,
            "action": decision.action,
            "quantity": decision.quantity,
            "price_used": str(price_used),
            "headline_len": len(headline) if headline else 0,
            "news_action": news.action.value if news else None,
            "news_sentiment": news.sentiment if news else None,
            "news_materiality": news.materiality if news else None,
            "news_event_type": news.event_type if news else None,
        }

    async def _log_run_once(self, result: RunResult, headline: str | None) -> None:
        payload = self._decision_payload(
            result.decision, result.news, result.price_used, headline
        )
        payload.update(
            {
                "submitted": result.submitted,
                "message": result.message,
                "order_result": result.order_result,
            }
        )
        await self._log_event("run_once", payload)

    async def _log_event(self, event: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self.audit.append, event, payload)

    async def start_loop(self) -> None:
        if not self.settings.bot_enabled:
            raise ValueError("BOT_ENABLED is false")
        if self.loop_running:
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop_loop(self) -> None:
        self._stop_event.set()
        if self._loop_task is not None:
            try:
                await asyncio.wait_for(self._loop_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._loop_task.cancel()
            self._loop_task = None

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                for symbol in self.settings.symbol_list:
                    if self._stop_event.is_set():
                        break
                    try:
                        await self.run_once(symbol)
                        self._last_error = None
                    except Exception as exc:
                        self._last_error = str(exc)
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.settings.bot_poll_interval_sec,
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            self._loop_task = None

    async def account_summary_masked(self) -> dict[str, Any]:
        summary = await asyncio.to_thread(self.broker.get_account_summary)
        summary["account_id"] = mask_account_id(str(summary.get("account_id", "")))
        return summary
