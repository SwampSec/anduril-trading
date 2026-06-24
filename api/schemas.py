from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    api_port: int
    bot_enabled: bool
    symbols: list[str]


class IBKRStatusResponse(BaseModel):
    connected: bool
    host: str
    port: int
    read_only: bool
    mode: str | None = None


class BotStatusResponse(BaseModel):
    enabled: bool
    armed: bool
    loop_running: bool
    kill_switch: bool
    read_only: bool
    connected: bool
    mode: str | None
    symbols: list[str]


class DecisionResponse(BaseModel):
    symbol: str
    action: str
    quantity: int
    mode: str


class NewsOverlayResponse(BaseModel):
    action: str
    sentiment: float
    materiality: float
    event_type: str


class AnalyzeResponse(BaseModel):
    decision: DecisionResponse
    news: NewsOverlayResponse | None = None
    price_used: Decimal


class RunOnceResponse(BaseModel):
    decision: DecisionResponse
    news: NewsOverlayResponse | None = None
    price_used: Decimal
    submitted: bool
    order_result: dict[str, Any] | None = None
    message: str


def decision_to_response(decision) -> DecisionResponse:
    return DecisionResponse(
        symbol=decision.symbol,
        action=decision.action,
        quantity=decision.quantity,
        mode=decision.mode,
    )


def news_to_response(news) -> NewsOverlayResponse:
    return NewsOverlayResponse(
        action=news.action.value,
        sentiment=news.sentiment,
        materiality=news.materiality,
        event_type=news.event_type,
    )
