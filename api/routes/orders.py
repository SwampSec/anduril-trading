from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_bot_service, get_broker, get_order_journal
from api.services.bot import BotService
from broker.ibkr_client import IBKRClient, IBKRRequestError
from journal.orders import OrderJournal

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def list_order_history(
    journal: Annotated[OrderJournal, Depends(get_order_journal)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    symbol: Annotated[str | None, Query(max_length=12)] = None,
) -> dict:
    records = journal.tail(limit, symbol=symbol.upper() if symbol else None)
    return {"count": len(records), "records": records}


@router.get("/summary")
async def order_summary(
    journal: Annotated[OrderJournal, Depends(get_order_journal)],
) -> dict:
    summary = journal.summary()
    return {"count": len(summary), "positions": summary}


@router.get("/open")
async def open_orders(
    broker: Annotated[IBKRClient, Depends(get_broker)],
) -> dict:
    try:
        orders = await asyncio.to_thread(broker.get_open_orders)
        return {"count": len(orders), "orders": orders}
    except IBKRRequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/sync")
async def sync_orders(
    service: Annotated[BotService, Depends(get_bot_service)],
) -> dict:
    try:
        return await service.sync_order_history()
    except IBKRRequestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
