from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ..cache import cache, CACHE_TTL_STATS
from ..config import get_settings
from ..db import get_repo_consistency_report, get_repo_stats
from ..deps import require_admin
from ..rate_limit import limiter, RATE_LIMIT_DEFAULT
from ..schemas import ConsistencyReportResponse, StatsResponse
from ..state import _get_quality_metrics

router = APIRouter()


@router.get("/metrics/quality")
async def quality_metrics_endpoint() -> dict:
    return await _get_quality_metrics()


@router.get(
    "/metrics/consistency",
    response_model=ConsistencyReportResponse,
    dependencies=[Depends(require_admin)],
)
async def consistency_metrics_endpoint() -> ConsistencyReportResponse:
    current = get_settings()
    return ConsistencyReportResponse(
        **(await get_repo_consistency_report(current.ai_taxonomy_path))
    )


@router.get("/stats", response_model=StatsResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def stats(
    request: Request,
    response: Response,
    refresh: bool = Query(default=False),
    snapshot: bool = Query(default=True),
) -> StatsResponse:
    response.headers["Cache-Control"] = "no-store"
    if not refresh and snapshot:
        cached = await cache.get("stats")
        if cached:
            return StatsResponse(**cached)
    data = await get_repo_stats(refresh=refresh, use_snapshot=snapshot)
    await cache.set("stats", data, CACHE_TTL_STATS)
    return StatsResponse(**data)
