import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .db import close_db_pool, init_db, init_db_pool, reset_stale_tasks
from .github import GitHubClient
from .ai_client import AIClient
from .observability import (
    REQUEST_ID_HEADER,
    bind_log_context,
    configure_logging,
    resolve_request_id,
)
from .rate_limit import limiter
from .routes import api_router
from .security import resolve_cors_policy, validate_security_baseline
from .state import (
    API_SEMAPHORE_LIMIT,
    TASK_STALE_MINUTES,
    _add_quality_metrics,
    classification_stop,
)

logger = logging.getLogger("starsorty.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_baseline(_init_settings.cors_origins)
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
        from . import state as _state
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


app = FastAPI(title="StarSorty API", version="0.2.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_init_settings = get_settings()
configure_logging(_init_settings.log_level)
origins, allow_credentials = resolve_cors_policy(_init_settings.cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    started = time.perf_counter()

    with bind_log_context(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000
            await _add_quality_metrics(
                api_request_total=1,
                api_error_total=1,
                api_request_latency_ms_total=int(round(latency_ms)),
            )
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                latency_ms,
            )
            raise

        latency_ms = (time.perf_counter() - started) * 1000
        await _add_quality_metrics(
            api_request_total=1,
            api_error_total=1 if response.status_code >= 500 or response.status_code == 429 else 0,
            api_request_latency_ms_total=int(round(latency_ms)),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    del exc
    request_id = getattr(request.state, "request_id", None) or resolve_request_id(
        request.headers.get(REQUEST_ID_HEADER)
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


app.include_router(api_router)
