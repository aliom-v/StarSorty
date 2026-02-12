import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .db import close_db_pool, init_db, init_db_pool, reset_stale_tasks
from .github import GitHubClient
from .ai_client import AIClient
from .rate_limit import limiter
from .routes import api_router
from .state import (
    API_SEMAPHORE_LIMIT,
    TASK_STALE_MINUTES,
    classification_stop,
    classification_task,
)

logger = logging.getLogger("starsorty.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    await init_db()
    stale = await reset_stale_tasks(TASK_STALE_MINUTES)
    if stale:
        logger.warning("Reset %s stale tasks at startup", stale)
    github_http = httpx.AsyncClient()
    ai_http = httpx.AsyncClient()
    app.state.github_client = GitHubClient(github_http, asyncio.Semaphore(API_SEMAPHORE_LIMIT))
    app.state.ai_client = AIClient(ai_http, asyncio.Semaphore(API_SEMAPHORE_LIMIT))
    try:
        yield
    finally:
        import api.app.state as _state
        if _state.classification_task is not None:
            classification_stop.set()
            _state.classification_task.cancel()
            try:
                await _state.classification_task
            except asyncio.CancelledError:
                pass
        await github_http.aclose()
        await ai_http.aclose()
        await close_db_pool()


app = FastAPI(title="StarSorty API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_init_settings = get_settings()
origins: List[str] = [origin.strip() for origin in _init_settings.cors_origins.split(",") if origin.strip()]
allow_credentials = True
if not origins or "*" in origins:
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
