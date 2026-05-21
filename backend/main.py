"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.v1.router import api_v1_router
from core.config import get_settings
from core.db import dispose_engine
from core.exceptions import register_exception_handlers
from core.logging import configure_logging
from core.redis_client import close_redis

_settings = get_settings()

configure_logging(
    log_level=_settings.LOG_LEVEL,
    json_logs=_settings.APP_ENV != "development",
)

# Side-effect import; registers every concrete agent in AgentRegistry.
import agents  # noqa: E402, F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()
    await close_redis()


app = FastAPI(
    title="AstroLearn",
    description="Multi-agent astronomy & learning backend.",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe (no DB/Redis hit)."""
    return {"status": "ok", "env": _settings.APP_ENV}
