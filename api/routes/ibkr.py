from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_bot_service, get_broker
from api.schemas import IBKRStatusResponse
from api.services.bot import BotService
from broker.ibkr_client import IBKRClient, IBKRReadOnlyError, IBKRRequestError

router = APIRouter(prefix="/ibkr", tags=["ibkr"])


@router.get("/status", response_model=IBKRStatusResponse)
async def ibkr_status(broker: Annotated[IBKRClient, Depends(get_broker)]) -> IBKRStatusResponse:
    mode = None
    if broker.connected:
        try:
            mode = broker.mode
        except Exception:
            mode = None
    return IBKRStatusResponse(
        connected=broker.connected,
        host=broker.config.host,
        port=broker.config.port,
        read_only=broker.config.read_only,
        mode=mode,
    )


@router.post("/connect")
async def ibkr_connect(service: Annotated[BotService, Depends(get_bot_service)]) -> dict:
    try:
        await service.connect()
        return {"connected": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/disconnect")
async def ibkr_disconnect(service: Annotated[BotService, Depends(get_bot_service)]) -> dict:
    await service.disconnect()
    return {"connected": False}


@router.get("/account")
async def ibkr_account(service: Annotated[BotService, Depends(get_bot_service)]) -> dict:
    try:
        return await service.account_summary_masked()
    except IBKRRequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/positions")
async def ibkr_positions(broker: Annotated[IBKRClient, Depends(get_broker)]) -> dict:
    try:
        positions = await asyncio.to_thread(broker.get_positions)
        return {symbol: str(qty) for symbol, qty in positions.items()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/quote")
async def ibkr_quote(
    broker: Annotated[IBKRClient, Depends(get_broker)],
    symbol: Annotated[str, Query(min_length=1, max_length=12)],
) -> dict:
    try:
        quote = await asyncio.to_thread(broker.get_quote, symbol.upper())
        price = quote.trade_price()
        return {
            "symbol": quote.symbol,
            "bid": str(quote.bid) if quote.bid is not None else None,
            "ask": str(quote.ask) if quote.ask is not None else None,
            "last": str(quote.last) if quote.last is not None else None,
            "trade_price": str(price) if price is not None else None,
            "as_of": quote.as_of.isoformat(),
        }
    except IBKRRequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders")
async def ibkr_orders(broker: Annotated[IBKRClient, Depends(get_broker)]) -> dict:
    try:
        orders = await asyncio.to_thread(broker.get_open_orders)
        return {"count": len(orders), "orders": orders}
    except IBKRRequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{order_id}/cancel")
async def ibkr_cancel_order(
    order_id: int,
    broker: Annotated[IBKRClient, Depends(get_broker)],
) -> dict:
    try:
        return await asyncio.to_thread(broker.cancel_order, order_id)
    except IBKRReadOnlyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IBKRRequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
