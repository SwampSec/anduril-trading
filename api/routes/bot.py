from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_bot_service
from api.schemas import (
    AnalyzeResponse,
    BotStatusResponse,
    RunOnceResponse,
    decision_to_response,
    news_to_response,
)
from api.services.bot import BotService
from risk.guardrails import RefuseToArm

router = APIRouter(prefix="/bot", tags=["bot"])


@router.get("/status", response_model=BotStatusResponse)
async def bot_status(service: Annotated[BotService, Depends(get_bot_service)]) -> BotStatusResponse:
    status = service.status()
    return BotStatusResponse(
        enabled=status.enabled,
        armed=status.armed,
        kill_switch=status.kill_switch,
        read_only=status.read_only,
        connected=status.connected,
        mode=status.mode,
        symbols=status.symbols,
    )


@router.post("/arm")
async def bot_arm(service: Annotated[BotService, Depends(get_bot_service)]) -> dict:
    try:
        await service.arm()
        return {"armed": True}
    except RefuseToArm as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/disarm")
async def bot_disarm(service: Annotated[BotService, Depends(get_bot_service)]) -> dict:
    await service.disarm()
    return {"armed": False}


@router.post("/reconcile")
async def bot_reconcile(service: Annotated[BotService, Depends(get_bot_service)]) -> dict:
    try:
        await service.reconcile()
        return {"reconciled": True}
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/analyze", response_model=AnalyzeResponse)
async def bot_analyze(
    service: Annotated[BotService, Depends(get_bot_service)],
    symbol: Annotated[str, Query(min_length=1, max_length=12)],
    price: Annotated[Decimal, Query(gt=0)],
    headline: Annotated[str | None, Query(max_length=4000)] = None,
) -> AnalyzeResponse:
    try:
        decision, news = await service.analyze(symbol, price, headline)
        return AnalyzeResponse(
            decision=decision_to_response(decision),
            news=news_to_response(news) if news else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/run-once", response_model=RunOnceResponse)
async def bot_run_once(
    service: Annotated[BotService, Depends(get_bot_service)],
    symbol: Annotated[str, Query(min_length=1, max_length=12)],
    price: Annotated[Decimal, Query(gt=0)],
    headline: Annotated[str | None, Query(max_length=4000)] = None,
) -> RunOnceResponse:
    try:
        result = await service.run_once(symbol, price, headline)
        return RunOnceResponse(
            decision=decision_to_response(result.decision),
            news=news_to_response(result.news) if result.news else None,
            submitted=result.submitted,
            order_result=result.order_result,
            message=result.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
