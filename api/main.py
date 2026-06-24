from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import get_bot_service
from api.routes import audit, bot, ibkr, llm, orders
from api.schemas import HealthResponse
from config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    service = get_bot_service()
    await service.stop_loop()
    await service.disconnect()


app = FastAPI(
    title="Anduril Trading API",
    description="Local control plane for IBKR paper trading and LM Studio overlays",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(audit.router)
app.include_router(orders.router)
app.include_router(ibkr.router)
app.include_router(llm.router)
app.include_router(bot.router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        api_port=settings.api_port,
        bot_enabled=settings.bot_enabled,
        symbols=settings.symbol_list,
    )
