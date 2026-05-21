from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ..cache_store import (
    cleanup_expired_shared_cache_entries,
    get_shared_cache_metrics,
)
from ..config import get_settings
from ..db import get_repo_consistency_report, get_repo_stats
from ..deps import require_admin
from ..rate_limit import limiter, RATE_LIMIT_DEFAULT
from ..schemas import (
    CacheCleanupResponse,
    CacheMetricsResponse,
    ConsistencyReportResponse,
    StatsResponse,
)
from ..state import _get_quality_metrics

router = APIRouter()


async def _build_cache_metrics_response() -> CacheMetricsResponse:
    shared = await get_shared_cache_metrics()
    quality = await _get_quality_metrics()
    return CacheMetricsResponse(
        entry_count=int(shared.get("entry_count", 0) or 0),
        expired_count=int(shared.get("expired_count", 0) or 0),
        approx_payload_bytes=int(shared.get("approx_payload_bytes", 0) or 0),
        namespaces=shared.get("namespaces", []),
        cache_hit_total=int(quality.get("cache_hit_total", 0) or 0),
        cache_local_hit_total=int(quality.get("cache_local_hit_total", 0) or 0),
        cache_shared_hit_total=int(quality.get("cache_shared_hit_total", 0) or 0),
        cache_miss_total=int(quality.get("cache_miss_total", 0) or 0),
        cache_hit_rate=float(quality.get("cache_hit_rate", 0.0) or 0.0),
        cache_local_hit_rate=float(quality.get("cache_local_hit_rate", 0.0) or 0.0),
        cache_shared_hit_rate=float(quality.get("cache_shared_hit_rate", 0.0) or 0.0),
    )


@router.get("/metrics/quality")
async def quality_metrics_endpoint() -> dict:
    return await _get_quality_metrics()


@router.get(
    "/metrics/cache",
    response_model=CacheMetricsResponse,
    dependencies=[Depends(require_admin)],
)
async def cache_metrics_endpoint() -> CacheMetricsResponse:
    return await _build_cache_metrics_response()


@router.post(
    "/metrics/cache/cleanup",
    response_model=CacheCleanupResponse,
    dependencies=[Depends(require_admin)],
)
async def cache_cleanup_endpoint(
    namespace: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
) -> CacheCleanupResponse:
    deleted_count = await cleanup_expired_shared_cache_entries(
        namespace=namespace,
        limit=limit,
    )
    return CacheCleanupResponse(
        deleted_count=deleted_count,
        metrics=await _build_cache_metrics_response(),
    )


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
    del request
    response.headers["Cache-Control"] = "no-store"
    data = await get_repo_stats(refresh=refresh, use_snapshot=snapshot)
    return StatsResponse(**data)
