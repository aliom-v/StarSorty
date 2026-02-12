import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..cache import cache, CACHE_TTL_REPOS
from ..db import (
    get_failed_repos,
    get_repo,
    get_user_interest_profile,
    list_override_history,
    list_repos,
    record_readme_fetch,
    reset_classify_fail_count,
    update_override,
)
from ..deps import (
    _normalize_preference_user,
    _normalized_optional,
    _repos_cache_key,
    require_admin,
)
from ..github import GitHubClient
from ..models import RepoBase
from ..rate_limit import limiter, RATE_LIMIT_DEFAULT
from ..schemas import (
    FailedReposResponse,
    OverrideHistoryResponse,
    OverrideRequest,
    OverrideResponse,
    ReadmeResponse,
    RepoListResponse,
    RepoOut,
    ResetFailedResponse,
)
from ..state import (
    REPOS_PAGE_LIMIT_MAX,
    SEARCH_RANKER_V2_ENABLED,
    TAG_FILTER_COUNT_MAX,
    _add_quality_metrics,
)

logger = logging.getLogger("starsorty.api")

router = APIRouter()


@router.get("/repos", response_model=RepoListResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def repos(
    request: Request,
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = Query(default=None, ge=0),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[str] = None,
    tag_mode: str = Query(default="or", pattern="^(and|or)$"),
    sort: str = Query(default="stars", pattern="^(relevance|stars|updated)$"),
    user_id: str = Query(default="global"),
    star_user: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=REPOS_PAGE_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
) -> RepoListResponse:
    q = _normalized_optional(q)
    language = _normalized_optional(language)
    category = _normalized_optional(category)
    subcategory = _normalized_optional(subcategory)
    tag = _normalized_optional(tag)
    star_user = _normalized_optional(star_user)
    tag_mode = (tag_mode or "or").strip().lower()
    sort = (sort or "stars").strip().lower()
    user_id = _normalize_preference_user(user_id)
    if not SEARCH_RANKER_V2_ENABLED and sort == "relevance":
        sort = "stars"

    tag_list = None
    normalized_tags = None
    if tags:
        tag_list = sorted({t.strip() for t in tags.split(",") if t.strip()})
        if len(tag_list) > TAG_FILTER_COUNT_MAX:
            tag_list = tag_list[:TAG_FILTER_COUNT_MAX]
        if tag_list:
            normalized_tags = ",".join(tag_list)
    cache_key = _repos_cache_key(
        q=q,
        language=language,
        min_stars=min_stars,
        category=category,
        subcategory=subcategory,
        tag=tag,
        tags=normalized_tags,
        tag_mode=tag_mode,
        sort=sort,
        user_id=user_id,
        star_user=star_user,
        limit=limit,
        offset=offset,
    )
    cached = await cache.get(cache_key)
    if cached is not None:
        return RepoListResponse(**cached)
    profile = await get_user_interest_profile(user_id)
    topic_scores = profile.get("topic_scores") if isinstance(profile, dict) else {}
    total, items = await list_repos(
        q=q,
        language=language,
        min_stars=min_stars,
        category=category,
        subcategory=subcategory,
        tag=tag,
        tags=tag_list,
        tag_mode=tag_mode,
        sort=sort,
        topic_scores=topic_scores if isinstance(topic_scores, dict) else None,
        star_user=star_user,
        limit=limit,
        offset=offset,
    )
    if q:
        await _add_quality_metrics(
            search_total=1,
            search_zero_result_total=1 if total == 0 else 0,
        )
    items_payload: List[dict] = []
    for item in items:
        payload = item.model_dump() if isinstance(item, RepoBase) else item
        items_payload.append(payload)
    items_out = [RepoOut(**payload) for payload in items_payload]
    response_payload = {"total": total, "items": items_payload}
    await cache.set(cache_key, response_payload, CACHE_TTL_REPOS)
    return RepoListResponse(total=total, items=items_out)


@router.get("/repos/failed", response_model=FailedReposResponse)
async def list_failed_repos_endpoint(min_fail_count: int = Query(default=5, ge=1, le=1000)) -> FailedReposResponse:
    items = await get_failed_repos(min_fail_count)
    return FailedReposResponse(items=items, total=len(items))


@router.post(
    "/repos/failed/reset",
    response_model=ResetFailedResponse,
    dependencies=[Depends(require_admin)],
)
async def reset_failed_repos() -> ResetFailedResponse:
    count = await reset_classify_fail_count()
    return ResetFailedResponse(reset_count=count)


@router.get("/repos/{full_name:path}", response_model=RepoOut)
async def repo_detail(full_name: str) -> RepoOut:
    repo = await get_repo(full_name)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    if isinstance(repo, RepoBase):
        return RepoOut(**repo.model_dump())
    return RepoOut(**repo)


@router.patch(
    "/repos/{full_name:path}/override",
    response_model=OverrideResponse,
    dependencies=[Depends(require_admin)],
)
async def repo_override(full_name: str, payload: OverrideRequest) -> OverrideResponse:
    fields = payload.model_fields_set
    updates: Dict[str, object] = {}
    if "category" in fields:
        if payload.category is not None and not str(payload.category).strip():
            raise HTTPException(status_code=400, detail="category cannot be empty")
        updates["category"] = payload.category
    if "subcategory" in fields:
        if payload.subcategory is not None and not str(payload.subcategory).strip():
            raise HTTPException(status_code=400, detail="subcategory cannot be empty")
        updates["subcategory"] = payload.subcategory
    if "tags" in fields:
        if payload.tags is None:
            updates["tags"] = None
        else:
            updates["tags"] = [tag for tag in payload.tags if str(tag).strip()]
    if "tag_ids" in fields:
        if payload.tag_ids is None:
            updates["tag_ids"] = None
        else:
            updates["tag_ids"] = [tag for tag in payload.tag_ids if str(tag).strip()]
    if "note" in fields:
        if payload.note is not None and not str(payload.note).strip():
            raise HTTPException(status_code=400, detail="note cannot be empty")
        updates["note"] = payload.note

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    updated = await update_override(full_name, updates)
    if not updated:
        if not await get_repo(full_name):
            raise HTTPException(status_code=404, detail="Repo not found")
        return OverrideResponse(updated=False)
    await cache.invalidate_prefix("stats")
    await cache.invalidate_prefix("repos")
    return OverrideResponse(updated=True)


@router.get("/repos/{full_name:path}/overrides", response_model=OverrideHistoryResponse)
async def repo_override_history(full_name: str) -> OverrideHistoryResponse:
    if not await get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    items = await list_override_history(full_name)
    return OverrideHistoryResponse(items=items)


@router.post(
    "/repos/{full_name:path}/readme",
    response_model=ReadmeResponse,
    dependencies=[Depends(require_admin)],
)
async def repo_readme(full_name: str, request: Request) -> ReadmeResponse:
    if not await get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    github_client: GitHubClient = request.app.state.github_client
    try:
        summary = await github_client.fetch_readme_summary(full_name)
    except Exception as exc:
        try:
            await record_readme_fetch(full_name, None, False)
        except Exception:
            logger.warning("Failed to record README fetch failure for %s", full_name)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        await record_readme_fetch(full_name, summary, True)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Failed to persist README summary. Please retry.",
        ) from exc
    await cache.invalidate_prefix("repos")
    return ReadmeResponse(updated=bool(summary), summary=summary)
