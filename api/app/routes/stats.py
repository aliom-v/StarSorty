from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from ..cache import cache, CACHE_TTL_STATS
from ..db import get_repo_stats
from ..rate_limit import limiter, RATE_LIMIT_DEFAULT
from ..schemas import StatsResponse
from ..state import _get_quality_metrics

router = APIRouter()


@router.get("/metrics/quality")
async def quality_metrics_endpoint() -> dict:
    return await _get_quality_metrics()


@router.get("/stats", response_model=StatsResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def stats(
    request: Request,
    response: Response,
    refresh: bool = Query(default=False),
) -> StatsResponse:
    response.headers["Cache-Control"] = "no-store"
    if not refresh:
        cached = await cache.get("stats")
        if cached:
            return StatsResponse(**cached)
    data = await get_repo_stats()
    await cache.set("stats", data, CACHE_TTL_STATS)
    return StatsResponse(**data)
