from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_bot_service, get_llm
from api.schemas import NewsOverlayResponse
from api.services.bot import BotService
from llm.client import LMStudioClient
from news.overlay import parse_news_signal

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/ping")
async def llm_ping(llm: Annotated[LMStudioClient, Depends(get_llm)]) -> dict:
    return llm.ping()


@router.post("/overlay", response_model=NewsOverlayResponse)
async def llm_overlay(
    llm: Annotated[LMStudioClient, Depends(get_llm)],
    headline: Annotated[str, Query(min_length=1, max_length=4000)],
) -> NewsOverlayResponse:
    try:
        import asyncio

        signal = await asyncio.to_thread(parse_news_signal, headline, llm)
        return NewsOverlayResponse(
            action=signal.action.value,
            sentiment=signal.sentiment,
            materiality=signal.materiality,
            event_type=signal.event_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
