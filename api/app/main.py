import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .rate_limit import limiter, RATE_LIMIT_DEFAULT, RATE_LIMIT_ADMIN, RATE_LIMIT_HEAVY
from .cache import cache, CACHE_TTL_STATS, CACHE_TTL_REPOS
from .db import (
    count_unclassified_repos,
    count_repos_for_classification,
    create_task,
    get_user_interest_profile,
    get_user_preferences,
    get_repo_stats,
    get_repo,
    get_task,
    get_sync_status,
    get_failed_repos,
    increment_classify_fail_count,
    init_db,
    init_db_pool,
    close_db_pool,
    iter_repos_for_export,
    list_override_history,
    list_repos,
    prune_star_user,
    prune_users_not_in,
    record_readme_fetch,
    record_readme_fetches,
    reset_classify_fail_count,
    reset_stale_tasks,
    record_user_feedback_event,
    select_repos_for_classification,
    list_training_samples,
    update_task,
    update_classification,
    update_classifications_bulk,
    update_user_preferences,
    update_override,
    update_sync_status,
    upsert_repos,
)
from .github import GitHubClient
from .models import RepoBase
from .ai_client import AIClient
from .taxonomy import load_taxonomy, normalize_tags_to_ids
from .rules import load_rules
from .classification.engine import ClassificationEngine
from .classification.decision import DecisionPolicy
from .settings_store import write_settings
from .export import generate_obsidian_zip, generate_obsidian_zip_streaming
import httpx
import uuid


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logging.getLogger("starsorty.api").warning(
            "Invalid %s=%r, fallback to %s",
            name,
            raw,
            default,
        )
        return default
    if minimum is not None and value < minimum:
        logging.getLogger("starsorty.api").warning(
            "Out-of-range %s=%r, fallback to %s",
            name,
            raw,
            default,
        )
        return default
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logging.getLogger("starsorty.api").warning(
            "Invalid %s=%r, fallback to %s",
            name,
            raw,
            default,
        )
        return default
    if minimum is not None and value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


API_SEMAPHORE_LIMIT = _env_int("API_SEMAPHORE_LIMIT", 5, minimum=1)
TASK_STALE_MINUTES = _env_int("TASK_STALE_MINUTES", 10, minimum=1)


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
        # Cancel background classification task if running
        if classification_task is not None:
            classification_stop.set()
            classification_task.cancel()
            try:
                await classification_task
            except asyncio.CancelledError:
                pass
        await github_http.aclose()
        await ai_http.aclose()
        await close_db_pool()


app = FastAPI(title="StarSorty API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
logger = logging.getLogger("starsorty.api")
DEFAULT_CLASSIFY_BATCH_SIZE = _env_int("CLASSIFY_BATCH_SIZE", 50, minimum=1)
DEFAULT_CLASSIFY_CONCURRENCY = _env_int("CLASSIFY_CONCURRENCY", 3, minimum=1)
CLASSIFY_CONCURRENCY_MAX = _env_int("CLASSIFY_CONCURRENCY_MAX", 10, minimum=1)
CLASSIFY_BATCH_SIZE_MAX = _env_int("CLASSIFY_BATCH_SIZE_MAX", 200, minimum=1)
REPOS_PAGE_LIMIT_MAX = _env_int("REPOS_PAGE_LIMIT_MAX", 200, minimum=1)
TAG_FILTER_COUNT_MAX = _env_int("TAG_FILTER_COUNT_MAX", 20, minimum=1)
CLASSIFY_BATCH_DELAY_MS = _env_int("CLASSIFY_BATCH_DELAY_MS", 0, minimum=0)
AI_CLASSIFY_BATCH_SIZE = _env_int("AI_CLASSIFY_BATCH_SIZE", 5, minimum=1)
CLASSIFY_REMAINING_REFRESH_EVERY = _env_int("CLASSIFY_REMAINING_REFRESH_EVERY", 5, minimum=1)
CLASSIFY_ENGINE_V2_ENABLED = _env_bool("CLASSIFY_ENGINE_V2_ENABLED", True)
SEARCH_RANKER_V2_ENABLED = _env_bool("SEARCH_RANKER_V2_ENABLED", True)
RULE_DIRECT_THRESHOLD = _env_float("RULE_DIRECT_THRESHOLD", 0.88, minimum=0.0, maximum=1.0)
RULE_AI_THRESHOLD = _env_float("RULE_AI_THRESHOLD", 0.45, minimum=0.0, maximum=1.0)

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
    allow_headers=["*"]
)

classification_lock = asyncio.Lock()
classification_stop = asyncio.Event()
classification_task: asyncio.Task | None = None
classification_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "failed": 0,
    "remaining": 0,
    "last_error": None,
    "batch_size": 0,
    "concurrency": 0,
    "task_id": None,
}
quality_metrics_lock = asyncio.Lock()
quality_metrics = {
    "classification_total": 0,
    "rule_hit_total": 0,
    "ai_fallback_total": 0,
    "empty_tag_total": 0,
    "uncategorized_total": 0,
    "search_total": 0,
    "search_zero_result_total": 0,
}

_admin_token_warned = False


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    global _admin_token_warned
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    if not admin_token:
        if not _admin_token_warned:
            logger.warning(
                "ADMIN_TOKEN is not set. Admin endpoints are unprotected. "
                "Set ADMIN_TOKEN environment variable for production use."
            )
            _admin_token_warned = True
        return
    if not secrets.compare_digest(x_admin_token or "", admin_token):
        raise HTTPException(status_code=401, detail="Admin token required")


def _normalize_provider(value: str) -> str:
    return str(value or "").strip().lower()


def _validate_ai_settings(current: "Settings") -> tuple[bool, str]:
    provider = _normalize_provider(current.ai_provider)
    if provider in ("", "none"):
        return False, "AI_PROVIDER is not configured"
    if not str(current.ai_model or "").strip():
        return False, "AI_MODEL is required for AI classification"
    if provider in ("openai", "anthropic") and not str(current.ai_api_key or "").strip():
        return False, f"AI_API_KEY is required for provider {provider}"
    if provider not in ("openai", "anthropic") and not str(current.ai_base_url or "").strip():
        return False, f"AI_BASE_URL is required for provider {provider or 'custom'}"
    return True, ""


def _resolve_classify_context(
    current: "Settings",
    rules: list,
    allow_fallback: bool,
) -> tuple[str, bool, str | None]:
    classify_mode = current.classify_mode
    rules_available = bool(rules)
    ai_ok, ai_reason = _validate_ai_settings(current)

    if classify_mode == "ai_only":
        if ai_ok:
            return classify_mode, True, None
        if allow_fallback and rules_available:
            return "rules_only", False, f"{ai_reason}. Falling back to rules_only."
        if allow_fallback:
            return classify_mode, False, f"{ai_reason}. Skipping classification."
        raise ValueError(ai_reason)

    if classify_mode == "rules_only":
        if rules_available:
            return classify_mode, False, None
        if allow_fallback and ai_ok:
            return "ai_only", True, "RULES_JSON is required for classify_mode=rules_only. Falling back to ai_only."
        if allow_fallback:
            return classify_mode, False, "RULES_JSON is required for classify_mode=rules_only."
        raise ValueError("RULES_JSON is required for classify_mode=rules_only")

    if rules_available or ai_ok:
        if not ai_ok and rules_available and allow_fallback:
            return "rules_only", False, f"{ai_reason}. Falling back to rules_only."
        return classify_mode, ai_ok, None

    if allow_fallback:
        return classify_mode, False, "AI_PROVIDER or RULES_JSON is required"
    raise ValueError("AI_PROVIDER or RULES_JSON is required")


async def _start_background_classify(
    payload: "BackgroundClassifyRequest",
    task_id: str,
    allow_fallback: bool = False,
) -> bool:
    global classification_task
    async with classification_lock:
        if classification_state["running"]:
            return False
        classification_stop.clear()
        classification_state["running"] = True
        classification_state["task_id"] = task_id
        classification_task = asyncio.create_task(
            _background_classify_loop(payload, allow_fallback, task_id)
        )
    return True


class SyncResponse(BaseModel):
    status: str
    queued_at: str
    count: int


class StatusResponse(BaseModel):
    last_sync_at: str | None
    last_result: str | None
    last_message: str | None


class TaskQueuedResponse(BaseModel):
    task_id: str
    status: str
    message: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    task_type: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    message: str | None
    result: dict | None
    cursor_full_name: str | None = None
    retry_from_task_id: str | None = None


class RepoOut(BaseModel):
    full_name: str
    name: str
    owner: str
    html_url: str
    description: str | None
    language: str | None
    stargazers_count: int | None
    forks_count: int | None
    topics: List[str]
    star_users: List[str]
    category: str | None
    subcategory: str | None
    tags: List[str]
    tag_ids: List[str] = Field(default_factory=list)
    ai_category: str | None
    ai_subcategory: str | None
    ai_confidence: float | None
    ai_tags: List[str]
    ai_tag_ids: List[str] = Field(default_factory=list)
    ai_keywords: List[str]
    ai_provider: str | None
    ai_model: str | None
    ai_reason: str | None = None
    ai_decision_source: str | None = None
    ai_rule_candidates: List[Dict[str, object]] = Field(default_factory=list)
    ai_updated_at: str | None
    override_category: str | None
    override_subcategory: str | None
    override_tags: List[str]
    override_tag_ids: List[str] = Field(default_factory=list)
    override_note: str | None
    override_summary_zh: str | None
    override_keywords: List[str]
    readme_summary: str | None
    readme_fetched_at: str | None
    pushed_at: str | None
    updated_at: str | None
    starred_at: str | None
    summary_zh: str | None
    keywords: List[str]
    search_score: float | None = None
    match_reasons: List[str] = Field(default_factory=list)


class RepoListResponse(BaseModel):
    total: int
    items: List[RepoOut]


class OverrideRequest(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
    tag_ids: Optional[List[str]] = None
    note: Optional[str] = None


class OverrideResponse(BaseModel):
    updated: bool


class OverrideHistoryItem(BaseModel):
    category: str | None
    subcategory: str | None
    tags: List[str]
    note: str | None
    updated_at: str | None


class OverrideHistoryResponse(BaseModel):
    items: List[OverrideHistoryItem]


class ClassifyRequest(BaseModel):
    limit: int = Field(default=20, ge=0)
    force: bool = False
    include_readme: bool = True
    preference_user: Optional[str] = "global"


class ClassifyResponse(BaseModel):
    total: int
    classified: int
    failed: int
    remaining_unclassified: int


class BackgroundClassifyRequest(ClassifyRequest):
    concurrency: Optional[int] = Field(default=None, ge=1)
    cursor_full_name: Optional[str] = None


class BackgroundClassifyResponse(BaseModel):
    started: bool
    running: bool
    message: str
    task_id: str | None = None


class BackgroundClassifyStatusResponse(BaseModel):
    running: bool
    started_at: str | None
    finished_at: str | None
    processed: int
    failed: int
    remaining: int
    last_error: str | None
    batch_size: int
    concurrency: int
    task_id: str | None = None


class UserPreferencesRequest(BaseModel):
    tag_mapping: Optional[Dict[str, str]] = None
    rule_priority: Optional[Dict[str, int]] = None


class UserPreferencesResponse(BaseModel):
    user_id: str
    tag_mapping: Dict[str, str]
    rule_priority: Dict[str, int]
    updated_at: str | None = None


class SearchFeedbackRequest(BaseModel):
    user_id: str = "global"
    query: str
    results_count: int = Field(default=0, ge=0)
    selected_tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    subcategory: Optional[str] = None


class ClickFeedbackRequest(BaseModel):
    user_id: str = "global"
    full_name: str
    query: Optional[str] = None


class FeedbackResponse(BaseModel):
    ok: bool


class InterestTopicItem(BaseModel):
    topic: str
    score: float


class InterestProfileResponse(BaseModel):
    user_id: str
    topic_scores: Dict[str, float]
    top_topics: List[InterestTopicItem]
    updated_at: str | None = None


class TrainingSampleItem(BaseModel):
    id: int
    user_id: str | None = None
    full_name: str
    before_category: str | None = None
    before_subcategory: str | None = None
    before_tag_ids: List[str] = Field(default_factory=list)
    after_category: str | None = None
    after_subcategory: str | None = None
    after_tag_ids: List[str] = Field(default_factory=list)
    note: str | None = None
    source: str | None = None
    created_at: str


class TrainingSamplesResponse(BaseModel):
    items: List[TrainingSampleItem]
    total: int


class FewShotItem(BaseModel):
    input: Dict[str, object]
    output: Dict[str, object]
    note: Optional[str] = None


class FewShotResponse(BaseModel):
    items: List[FewShotItem]
    total: int


class ReadmeResponse(BaseModel):
    updated: bool
    summary: str


class TaxonomyCategory(BaseModel):
    name: str
    subcategories: List[str] = Field(default_factory=list)


class TaxonomyTagDef(BaseModel):
    id: str
    zh: str
    group: str


class TaxonomyResponse(BaseModel):
    categories: List[TaxonomyCategory]
    tags: List[str]
    tag_defs: List[TaxonomyTagDef] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    github_username: str
    github_target_username: str
    github_usernames: str
    github_include_self: bool
    github_mode: str
    classify_mode: str
    auto_classify_after_sync: bool
    rules_json: str
    sync_cron: str
    sync_timeout: int
    github_token_set: bool
    ai_api_key_set: bool


class SettingsRequest(BaseModel):
    github_username: Optional[str] = None
    github_target_username: Optional[str] = None
    github_usernames: Optional[str] = None
    github_include_self: Optional[bool] = None
    github_mode: Optional[str] = None
    classify_mode: Optional[str] = None
    auto_classify_after_sync: Optional[bool] = None
    rules_json: Optional[str] = None
    sync_cron: Optional[str] = None
    sync_timeout: Optional[int] = Field(default=None, ge=1, le=3600)


class ClientSettingsResponse(BaseModel):
    github_mode: str
    classify_mode: str
    auto_classify_after_sync: bool


class StatsItem(BaseModel):
    name: str
    count: int


class SubcategoryStatsItem(StatsItem):
    category: str


class StatsResponse(BaseModel):
    total: int
    unclassified: int
    categories: List[StatsItem]
    subcategories: List[SubcategoryStatsItem]
    tags: List[StatsItem]
    users: List[StatsItem]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repos_cache_key(
    q: Optional[str],
    language: Optional[str],
    min_stars: Optional[int],
    category: Optional[str],
    subcategory: Optional[str],
    tag: Optional[str],
    tags: Optional[str],
    tag_mode: str,
    sort: str,
    user_id: str,
    star_user: Optional[str],
    limit: int,
    offset: int,
) -> str:
    payload = {
        "q": q,
        "language": language,
        "min_stars": min_stars,
        "category": category,
        "subcategory": subcategory,
        "tag": tag,
        "tags": tags,
        "tag_mode": tag_mode,
        "sort": sort,
        "user_id": user_id,
        "star_user": star_user,
        "limit": limit,
        "offset": offset,
    }
    return f"repos:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"


def _normalized_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_preference_user(value: Optional[str]) -> str:
    normalized = str(value or "global").strip()
    return normalized or "global"


def _apply_rule_priority_overrides(
    rules: List[Dict[str, object]],
    preference: Dict[str, object],
) -> List[Dict[str, object]]:
    priority_map_raw = preference.get("rule_priority") if isinstance(preference, dict) else {}
    if not isinstance(priority_map_raw, dict) or not priority_map_raw:
        return list(rules)
    adjusted: List[Dict[str, object]] = []
    for rule in rules:
        copied = dict(rule)
        rule_id = str(copied.get("rule_id") or "").strip()
        delta = priority_map_raw.get(rule_id)
        if delta is not None:
            try:
                copied["priority"] = int(copied.get("priority", 0)) + int(delta)
            except (TypeError, ValueError):
                pass
        adjusted.append(copied)
    return adjusted


def _resolve_tag_mapping(
    taxonomy: dict,
    preference: Dict[str, object],
) -> Dict[str, str]:
    mapping_raw = preference.get("tag_mapping") if isinstance(preference, dict) else {}
    if not isinstance(mapping_raw, dict):
        return {}
    tag_mapping: Dict[str, str] = {}
    for source, target in mapping_raw.items():
        source_ids = normalize_tags_to_ids([str(source)], taxonomy)
        target_ids = normalize_tags_to_ids([str(target)], taxonomy)
        if not source_ids or not target_ids:
            continue
        tag_mapping[source_ids[0]] = target_ids[0]
    return tag_mapping


def _apply_tag_mapping_to_result(result: Dict[str, object], mapping: Dict[str, str], taxonomy: dict) -> Dict[str, object]:
    if not mapping:
        return result
    tag_ids = [str(v) for v in (result.get("tag_ids") or []) if str(v).strip()]
    if not tag_ids:
        tag_ids = normalize_tags_to_ids([str(v) for v in (result.get("tags") or [])], taxonomy)
    remapped: List[str] = []
    seen: set[str] = set()
    for tag_id in tag_ids:
        mapped = mapping.get(tag_id, tag_id)
        if mapped in seen:
            continue
        seen.add(mapped)
        remapped.append(mapped)
    tag_id_to_name = taxonomy.get("tag_id_to_name") or {}
    mapped_tags = [tag_id_to_name.get(tag_id, tag_id) for tag_id in remapped]
    updated = dict(result)
    updated["tag_ids"] = remapped
    updated["tags"] = mapped_tags
    return updated


async def _register_task(
    task_id: str,
    task_type: str,
    message: str | None = None,
    payload: dict | None = None,
    retry_from_task_id: str | None = None,
) -> None:
    await create_task(
        task_id,
        task_type,
        status="queued",
        message=message,
        payload=payload,
        retry_from_task_id=retry_from_task_id,
    )


async def _set_task_status(task_id: str, status: str, **updates: object) -> None:
    await update_task(
        task_id,
        status,
        started_at=updates.get("started_at"),
        finished_at=updates.get("finished_at"),
        message=updates.get("message"),
        result=updates.get("result"),
        cursor_full_name=updates.get("cursor_full_name"),
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/auth/check", dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_ADMIN)
async def auth_check(request: Request) -> dict:
    return {"ok": True}


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def task_status(task_id: str) -> TaskStatusResponse:
    task = await get_task(task_id)
    if not task:
        inferred_type = "missing"
        try:
            uuid.UUID(task_id)
            inferred_type = "expired"
        except (ValueError, TypeError, AttributeError):
            inferred_type = "missing"
        now = _now_iso()
        return TaskStatusResponse(
            task_id=task_id,
            status="failed",
            task_type=inferred_type,
            created_at=now,
            started_at=None,
            finished_at=now,
            message="Task record unavailable (expired or cleaned)",
            result=None,
            cursor_full_name=None,
            retry_from_task_id=None,
        )
    response_data = {key: task.get(key) for key in TaskStatusResponse.model_fields}
    return TaskStatusResponse(**response_data)


@app.post(
    "/tasks/{task_id}/retry",
    response_model=TaskQueuedResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def retry_task(task_id: str) -> TaskQueuedResponse:
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("task_type") != "classify":
        raise HTTPException(status_code=400, detail="Retry is only supported for classify tasks")
    if task.get("status") in ("running", "processing", "queued"):
        raise HTTPException(status_code=409, detail="Task is still running or queued")
    payload = task.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Task payload not found")

    cursor_full_name = task.get("cursor_full_name")
    try:
        request_payload = BackgroundClassifyRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid task payload: {exc}") from exc
    if request_payload.force and cursor_full_name:
        request_payload = BackgroundClassifyRequest(
            **{**request_payload.model_dump(), "cursor_full_name": cursor_full_name}
        )

    new_task_id = str(uuid.uuid4())
    await _register_task(
        new_task_id,
        "classify",
        f"Retry of {task_id}",
        payload=request_payload.model_dump(),
        retry_from_task_id=task_id,
    )
    started = await _start_background_classify(request_payload, new_task_id, allow_fallback=False)
    if not started:
        await _set_task_status(
            new_task_id,
            "failed",
            finished_at=_now_iso(),
            message="Classification already running",
        )
        raise HTTPException(status_code=409, detail="Classification already running")
    logger.info("Queued retry task %s from %s", new_task_id, task_id)
    return TaskQueuedResponse(task_id=new_task_id, status="queued", message="Retry queued")


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    status_data = await get_sync_status()
    return StatusResponse(**status_data)


async def _run_sync_task(task_id: str) -> None:
    await _set_task_status(task_id, "running", started_at=_now_iso())
    current = get_settings()
    github_client: GitHubClient = app.state.github_client
    try:
        targets = await github_client.resolve_targets()
    except Exception as exc:
        await update_sync_status("error", str(exc))
        await _set_task_status(
            task_id,
            "failed",
            finished_at=_now_iso(),
            message=str(exc),
        )
        return

    total = 0
    removed_total = 0
    deleted_total = 0
    try:
        for username, use_auth in targets:
            repos = await github_client.fetch_starred_repos_for_user(username, use_auth)
            for repo in repos:
                repo.star_users = [username]
            repo_payloads = [repo.model_dump() for repo in repos]
            total += await upsert_repos(repo_payloads)
            keep_names = [repo.full_name for repo in repos if repo.full_name]
            removed, deleted = await prune_star_user(username, keep_names)
            removed_total += removed
            deleted_total += deleted

        allowed_users = [name for name, _ in targets]
        cleaned_total, cleaned_deleted = await prune_users_not_in(allowed_users)

        timestamp = await update_sync_status(
            "ok",
            (
                f"synced {total} repos, pruned {removed_total} stars, removed {deleted_total} repos, "
                f"cleaned {cleaned_total} repos, removed {cleaned_deleted} repos"
            ),
        )
    except Exception as exc:
        await update_sync_status("error", str(exc))
        await _set_task_status(
            task_id,
            "failed",
            finished_at=_now_iso(),
            message=str(exc),
        )
        return

    await _set_task_status(
        task_id,
        "finished",
        finished_at=_now_iso(),
        result={
            "count": total,
            "queued_at": timestamp,
        },
    )

    await cache.invalidate_prefix("stats")
    await cache.invalidate_prefix("repos")

    if current.auto_classify_after_sync:
        classify_task_id = str(uuid.uuid4())
        auto_payload = BackgroundClassifyRequest(
            limit=DEFAULT_CLASSIFY_BATCH_SIZE,
            force=False,
            include_readme=True,
            concurrency=DEFAULT_CLASSIFY_CONCURRENCY,
        )
        await _register_task(
            classify_task_id,
            "classify",
            "Auto classify after sync",
            payload=auto_payload.model_dump(),
        )
        started = await _start_background_classify(
            auto_payload,
            classify_task_id,
            allow_fallback=True,
        )
        if not started:
            await _set_task_status(
                classify_task_id,
                "failed",
                finished_at=_now_iso(),
                message="Classification already running",
            )


def _handle_task_exception(task: asyncio.Task) -> None:
    """Callback to log exceptions from fire-and-forget tasks."""
    try:
        exc = task.exception()
        if exc is not None:
            logger.error("Background task failed: %s", exc, exc_info=exc)
    except asyncio.CancelledError:
        pass


@app.post("/sync", response_model=TaskQueuedResponse, status_code=202, dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_HEAVY)
async def sync(request: Request) -> TaskQueuedResponse:
    task_id = str(uuid.uuid4())
    await _register_task(task_id, "sync", payload={})
    bg_task = asyncio.create_task(_run_sync_task(task_id))
    bg_task.add_done_callback(_handle_task_exception)
    return TaskQueuedResponse(task_id=task_id, status="queued", message="Sync queued")


@app.get("/repos", response_model=RepoListResponse)
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


@app.get("/export/obsidian")
@limiter.limit(RATE_LIMIT_HEAVY)
async def export_obsidian(
    request: Request,
    tags: Optional[str] = None,
    language: Optional[str] = None,
) -> Response:
    """Export all repos as Obsidian-compatible Markdown files in a ZIP."""
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    # Use streaming to avoid loading all repos into memory at once
    repo_iter = iter_repos_for_export(language=language, tags=tag_list)
    zip_bytes = await generate_obsidian_zip_streaming(repo_iter)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="starsorty-export.zip"'},
    )


class FailedRepoItem(BaseModel):
    full_name: str
    name: str
    owner: str
    description: Optional[str] = None
    language: Optional[str] = None
    classify_fail_count: int


class FailedReposResponse(BaseModel):
    items: List[FailedRepoItem]
    total: int


class ResetFailedResponse(BaseModel):
    reset_count: int


@app.get("/repos/failed", response_model=FailedReposResponse)
async def list_failed_repos(min_fail_count: int = Query(default=5, ge=1, le=1000)) -> FailedReposResponse:
    """List repos that have failed classification multiple times."""
    items = await get_failed_repos(min_fail_count)
    return FailedReposResponse(items=items, total=len(items))


@app.post(
    "/repos/failed/reset",
    response_model=ResetFailedResponse,
    dependencies=[Depends(require_admin)],
)
async def reset_failed_repos() -> ResetFailedResponse:
    """Reset classify_fail_count for all repos, allowing them to be retried."""
    count = await reset_classify_fail_count()
    return ResetFailedResponse(reset_count=count)


@app.get("/repos/{full_name:path}", response_model=RepoOut)
async def repo_detail(full_name: str) -> RepoOut:
    repo = await get_repo(full_name)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    if isinstance(repo, RepoBase):
        return RepoOut(**repo.model_dump())
    return RepoOut(**repo)


@app.patch(
    "/repos/{full_name:path}/override",
    response_model=OverrideResponse,
    dependencies=[Depends(require_admin)],
)
async def repo_override(full_name: str, payload: OverrideRequest) -> OverrideResponse:
    fields = payload.model_fields_set
    updates: Dict[str, Optional[object]] = {}
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


@app.get("/repos/{full_name:path}/overrides", response_model=OverrideHistoryResponse)
async def repo_override_history(full_name: str) -> OverrideHistoryResponse:
    if not await get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    items = await list_override_history(full_name)
    return OverrideHistoryResponse(items=items)


@app.post(
    "/repos/{full_name:path}/readme",
    response_model=ReadmeResponse,
    dependencies=[Depends(require_admin)],
)
async def repo_readme(full_name: str) -> ReadmeResponse:
    if not await get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    github_client: GitHubClient = app.state.github_client
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


@app.get("/taxonomy", response_model=TaxonomyResponse)
async def taxonomy() -> TaxonomyResponse:
    current = get_settings()
    data = load_taxonomy(current.ai_taxonomy_path)
    return TaxonomyResponse(
        categories=data.get("categories", []),
        tags=data.get("tags", []),
        tag_defs=data.get("tag_defs", []),
    )


@app.get("/preferences/{user_id}", response_model=UserPreferencesResponse)
async def get_preferences(user_id: str) -> UserPreferencesResponse:
    preference = await get_user_preferences(_normalize_preference_user(user_id))
    return UserPreferencesResponse(**preference)


@app.patch(
    "/preferences/{user_id}",
    response_model=UserPreferencesResponse,
    dependencies=[Depends(require_admin)],
)
async def patch_preferences(user_id: str, payload: UserPreferencesRequest) -> UserPreferencesResponse:
    updated = await update_user_preferences(
        _normalize_preference_user(user_id),
        tag_mapping=payload.tag_mapping,
        rule_priority=payload.rule_priority,
    )
    return UserPreferencesResponse(**updated)


@app.post("/feedback/search", response_model=FeedbackResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def feedback_search(request: Request, payload: SearchFeedbackRequest) -> FeedbackResponse:
    await record_user_feedback_event(
        user_id=_normalize_preference_user(payload.user_id),
        event_type="search",
        query=payload.query,
        payload={
            "query": payload.query,
            "results_count": payload.results_count,
            "tags": payload.selected_tags,
            "category": payload.category,
            "subcategory": payload.subcategory,
        },
    )
    return FeedbackResponse(ok=True)


@app.post("/feedback/click", response_model=FeedbackResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def feedback_click(request: Request, payload: ClickFeedbackRequest) -> FeedbackResponse:
    await record_user_feedback_event(
        user_id=_normalize_preference_user(payload.user_id),
        event_type="click",
        query=payload.query,
        full_name=payload.full_name,
        payload={
            "query": payload.query,
        },
    )
    return FeedbackResponse(ok=True)


@app.get("/interest/{user_id}", response_model=InterestProfileResponse)
async def interest_profile(user_id: str) -> InterestProfileResponse:
    profile = await get_user_interest_profile(_normalize_preference_user(user_id))
    return InterestProfileResponse(**profile)


@app.get(
    "/training/samples",
    response_model=TrainingSamplesResponse,
    dependencies=[Depends(require_admin)],
)
async def training_samples(
    user_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> TrainingSamplesResponse:
    items = await list_training_samples(_normalized_optional(user_id), limit=limit)
    return TrainingSamplesResponse(items=[TrainingSampleItem(**item) for item in items], total=len(items))


@app.get(
    "/training/fewshot",
    response_model=FewShotResponse,
    dependencies=[Depends(require_admin)],
)
async def training_fewshot(
    user_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> FewShotResponse:
    samples = await list_training_samples(_normalized_optional(user_id), limit=limit)
    items: List[FewShotItem] = []
    for sample in samples:
        repo = await get_repo(sample["full_name"])
        if not repo:
            continue
        repo_payload = repo.model_dump() if isinstance(repo, RepoBase) else dict(repo)
        items.append(
            FewShotItem(
                input={
                    "full_name": repo_payload.get("full_name"),
                    "name": repo_payload.get("name"),
                    "description": repo_payload.get("description"),
                    "topics": repo_payload.get("topics") or [],
                    "readme_summary": repo_payload.get("readme_summary"),
                },
                output={
                    "category": sample.get("after_category"),
                    "subcategory": sample.get("after_subcategory"),
                    "tag_ids": sample.get("after_tag_ids") or [],
                },
                note=sample.get("note"),
            )
        )
    return FewShotResponse(items=items, total=len(items))


async def _update_classification_state(**updates: object) -> None:
    async with classification_lock:
        classification_state.update(updates)


async def _get_classification_state() -> dict:
    async with classification_lock:
        return dict(classification_state)


async def _add_quality_metrics(**delta: int) -> None:
    async with quality_metrics_lock:
        for key, value in delta.items():
            if key not in quality_metrics:
                continue
            quality_metrics[key] = int(quality_metrics.get(key, 0) or 0) + int(value or 0)


async def _get_quality_metrics() -> dict:
    async with quality_metrics_lock:
        data = dict(quality_metrics)
    classification_total = max(1, int(data.get("classification_total", 0)))
    search_total = max(1, int(data.get("search_total", 0)))
    data["rule_hit_rate"] = data.get("rule_hit_total", 0) / classification_total
    data["ai_fallback_rate"] = data.get("ai_fallback_total", 0) / classification_total
    data["empty_tag_rate"] = data.get("empty_tag_total", 0) / classification_total
    data["uncategorized_rate"] = data.get("uncategorized_total", 0) / classification_total
    data["search_zero_result_rate"] = data.get("search_zero_result_total", 0) / search_total
    return data


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _should_fetch_readme(repo_data: dict) -> bool:
    description = (repo_data.get("description") or "").strip()
    if len(description) >= 20:
        return False
    if repo_data.get("readme_summary"):
        return False
    if repo_data.get("readme_empty"):
        return False
    failures = int(repo_data.get("readme_failures") or 0)
    if failures >= 3:
        return False
    last_attempt = _parse_timestamp(repo_data.get("readme_last_attempt_at"))
    if last_attempt:
        now = datetime.now(timezone.utc)
        if now - last_attempt < timedelta(minutes=1):
            return False
    return True


def _chunk_repos(items: list, size: int) -> list[list]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _classify_repo_once(
    repo: dict,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    include_readme: bool,
    github_client: GitHubClient,
    ai_client: AIClient,
) -> bool:
    if isinstance(repo, RepoBase):
        repo_data = repo.model_dump()
    else:
        repo_data = dict(repo)
    if include_readme:
        if _should_fetch_readme(repo_data):
            summary = ""
            try:
                summary = await github_client.fetch_readme_summary(repo_data["full_name"])
            except Exception:
                try:
                    await record_readme_fetch(repo_data["full_name"], None, False)
                except Exception:
                    logger.warning(
                        "Failed to record README fetch failure for %s",
                        repo_data.get("full_name"),
                    )
            else:
                try:
                    await record_readme_fetch(repo_data["full_name"], summary, True)
                except Exception as exc:
                    logger.warning(
                        "Failed to persist README summary for %s: %s",
                        repo_data.get("full_name"),
                        exc,
                    )
            if summary:
                repo_data["readme_summary"] = summary
    if CLASSIFY_ENGINE_V2_ENABLED:
        policy = DecisionPolicy(
            direct_rule_threshold=RULE_DIRECT_THRESHOLD,
            ai_required_threshold=RULE_AI_THRESHOLD,
        )
    else:
        policy = DecisionPolicy(direct_rule_threshold=0.0, ai_required_threshold=1.0)
    engine = ClassificationEngine(
        taxonomy=data,
        rules=rules,
        classify_mode=classify_mode,
        use_ai=use_ai,
        policy=policy,
    )
    outcome = await engine.classify_repo(repo_data, ai_client, ai_retries=2)
    result = outcome.result
    provider = result.get("provider") if outcome.source == "ai" else "rules"
    model = result.get("model") if outcome.source == "ai" else "rules"
    if outcome.source == "manual_review":
        provider = "manual"
        model = "manual"
    rule_candidates = [
        {
            "rule_id": candidate.rule_id,
            "score": candidate.score,
            "category": candidate.category,
            "subcategory": candidate.subcategory,
            "evidence": candidate.evidence,
            "tag_ids": candidate.tag_ids,
        }
        for candidate in outcome.rule_candidates[:5]
    ]
    await update_classification(
        repo_data["full_name"],
        result["category"],
        result["subcategory"],
        result["confidence"],
        result["tags"],
        result.get("tag_ids"),
        provider,
        model,
        summary_zh=result.get("summary_zh"),
        keywords=result.get("keywords"),
        reason=str(result.get("reason") or outcome.reason or "")[:500],
        decision_source=outcome.source,
        rule_candidates=rule_candidates,
    )
    return True


async def _classify_repos_batch(
    repos: list,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    preference: dict,
    include_readme: bool,
    github_client: GitHubClient,
    ai_client: AIClient,
    task_id: str | None = None,
) -> tuple[int, int]:
    classified = 0
    failed = 0
    repo_datas: list[dict] = []
    readme_targets: list[dict] = []
    all_full_names: set[str] = set()
    success_full_names: set[str] = set()

    for repo in repos:
        if isinstance(repo, RepoBase):
            repo_data = repo.model_dump()
        else:
            repo_data = dict(repo)
        if include_readme and _should_fetch_readme(repo_data):
            readme_targets.append(repo_data)
        repo_datas.append(repo_data)
        full_name = repo_data.get("full_name")
        if full_name:
            all_full_names.add(full_name)

    # Concurrent README fetching
    if include_readme and readme_targets:
        async def fetch_readme(target: dict) -> dict:
            try:
                summary = await github_client.fetch_readme_summary(target["full_name"])
                return {"full_name": target["full_name"], "summary": summary, "success": True}
            except Exception as exc:
                # Log non-404 errors for diagnosis (rate limits, auth issues, etc.)
                logger.debug(
                    "README fetch failed for %s: %s",
                    target.get("full_name"),
                    exc,
                )
                return {"full_name": target["full_name"], "summary": None, "success": False}

        results = await asyncio.gather(
            *(fetch_readme(target) for target in readme_targets),
            return_exceptions=True,
        )
        readme_updates: list[dict] = []
        for target, result in zip(readme_targets, results):
            if isinstance(result, Exception):
                logger.warning(
                    "README fetch raised unexpected exception for %s: %s",
                    target.get("full_name"),
                    result,
                )
                readme_updates.append(
                    {"full_name": target.get("full_name"), "summary": None, "success": False}
                )
                continue
            readme_updates.append(result)
            if result.get("success") and result.get("summary"):
                target["readme_summary"] = result["summary"]

        if readme_updates:
            try:
                await record_readme_fetches(readme_updates)
            except Exception as exc:
                logger.warning("Failed to persist README batch updates: %s", exc)
                for update in readme_updates:
                    full_name = update.get("full_name")
                    if not full_name:
                        continue
                    try:
                        await record_readme_fetch(
                            full_name,
                            update.get("summary"),
                            bool(update.get("success")),
                        )
                    except Exception:
                        logger.warning(
                            "Failed to record README fetch failure for %s",
                            full_name,
                        )

    effective_rules = _apply_rule_priority_overrides(rules, preference)
    tag_mapping = _resolve_tag_mapping(data, preference)

    if CLASSIFY_ENGINE_V2_ENABLED:
        policy = DecisionPolicy(
            direct_rule_threshold=RULE_DIRECT_THRESHOLD,
            ai_required_threshold=RULE_AI_THRESHOLD,
        )
    else:
        policy = DecisionPolicy(direct_rule_threshold=0.0, ai_required_threshold=1.0)
    engine = ClassificationEngine(
        taxonomy=data,
        rules=effective_rules,
        classify_mode=classify_mode,
        use_ai=use_ai,
        policy=policy,
    )
    updates: list[dict] = []
    metric_classification_total = 0
    metric_rule_hit_total = 0
    metric_ai_fallback_total = 0
    metric_empty_tag_total = 0
    metric_uncategorized_total = 0

    for repo_data in repo_datas:
        full_name = repo_data.get("full_name")
        if not full_name:
            failed += 1
            continue
        started = time.perf_counter()
        try:
            outcome = await engine.classify_repo(repo_data, ai_client, ai_retries=2)
            result = _apply_tag_mapping_to_result(outcome.result, tag_mapping, data)
            provider = result.get("provider") if outcome.source == "ai" else "rules"
            model = result.get("model") if outcome.source == "ai" else "rules"
            if outcome.source == "manual_review":
                provider = "manual"
                model = "manual"
            updates.append(
                {
                    "full_name": full_name,
                    "category": result["category"],
                    "subcategory": result["subcategory"],
                    "confidence": result["confidence"],
                    "tags": result["tags"],
                    "tag_ids": result.get("tag_ids") or [],
                    "provider": provider,
                    "model": model,
                    "summary_zh": result.get("summary_zh"),
                    "keywords": result.get("keywords"),
                    "reason": str(result.get("reason") or outcome.reason or "")[:500],
                    "decision_source": outcome.source,
                    "rule_candidates": [
                        {
                            "rule_id": candidate.rule_id,
                            "score": candidate.score,
                            "category": candidate.category,
                            "subcategory": candidate.subcategory,
                            "evidence": candidate.evidence,
                            "tag_ids": candidate.tag_ids,
                        }
                        for candidate in outcome.rule_candidates[:5]
                    ],
                }
            )
            metric_classification_total += 1
            if outcome.source in ("rules", "rules_fallback"):
                metric_rule_hit_total += 1
            if outcome.source == "rules_fallback":
                metric_ai_fallback_total += 1
            if not result.get("tags"):
                metric_empty_tag_total += 1
            if str(result.get("category") or "") in ("uncategorized", "other", ""):
                metric_uncategorized_total += 1
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "classification_event %s",
                json.dumps(
                    {
                        "task_id": task_id,
                        "repo": full_name,
                        "rule_candidates": updates[-1]["rule_candidates"],
                        "final_decision": {
                            "source": outcome.source,
                            "category": result.get("category"),
                            "subcategory": result.get("subcategory"),
                            "confidence": result.get("confidence"),
                        },
                        "latency_ms": round(latency_ms, 2),
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Classification failed for %s: %s", full_name, exc)
            failed += 1

    if updates:
        try:
            await update_classifications_bulk(updates)
            classified += len(updates)
            for item in updates:
                if item.get("full_name"):
                    success_full_names.add(item["full_name"])
        except Exception as exc:
            logger.warning("Bulk classification update failed: %s", exc)
            for item in updates:
                full_name = item.get("full_name")
                if not full_name:
                    failed += 1
                    continue
                try:
                    await update_classification(
                        full_name,
                        item["category"],
                        item["subcategory"],
                        item["confidence"],
                        item["tags"],
                        item.get("tag_ids"),
                        item["provider"],
                        item["model"],
                        summary_zh=item.get("summary_zh"),
                        keywords=item.get("keywords"),
                        reason=item.get("reason"),
                        decision_source=item.get("decision_source"),
                        rule_candidates=item.get("rule_candidates"),
                    )
                    classified += 1
                    success_full_names.add(full_name)
                except Exception:
                    failed += 1

    # Increment fail count for repos that failed classification
    failed_full_names = list(all_full_names - success_full_names)
    if failed_full_names:
        try:
            await increment_classify_fail_count(failed_full_names)
            logger.debug("Incremented fail count for %d repos", len(failed_full_names))
        except Exception as exc:
            logger.warning("Failed to increment classify_fail_count: %s", exc)

    if metric_classification_total > 0:
        await _add_quality_metrics(
            classification_total=metric_classification_total,
            rule_hit_total=metric_rule_hit_total,
            ai_fallback_total=metric_ai_fallback_total,
            empty_tag_total=metric_empty_tag_total,
            uncategorized_total=metric_uncategorized_total,
        )

    return (classified, failed)


async def _classify_repos_concurrent(
    repos_to_classify: list,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    preference: dict,
    include_readme: bool,
    concurrency: int,
    github_client: GitHubClient,
    ai_client: AIClient,
    task_id: str | None = None,
) -> tuple[int, int]:
    batches = _chunk_repos(repos_to_classify, AI_CLASSIFY_BATCH_SIZE)
    if concurrency <= 1 or len(batches) <= 1:
        classified = 0
        failed = 0
        for batch in batches:
            try:
                batch_classified, batch_failed = await _classify_repos_batch(
                    batch,
                    data,
                    rules,
                    classify_mode,
                    use_ai,
                    preference,
                    include_readme,
                    github_client,
                    ai_client,
                    task_id,
                )
                classified += batch_classified
                failed += batch_failed
            except Exception:
                failed += len(batch)
        return (classified, failed)

    classified = 0
    failed = 0
    counter_lock = asyncio.Lock()
    queue: asyncio.Queue[Optional[list]] = asyncio.Queue()
    for batch in batches:
        queue.put_nowait(batch)
    for _ in range(concurrency):
        queue.put_nowait(None)

    async def worker() -> None:
        nonlocal classified, failed
        while True:
            batch = await queue.get()
            if batch is None:
                queue.task_done()
                break
            try:
                batch_classified, batch_failed = await _classify_repos_batch(
                    batch,
                    data,
                    rules,
                    classify_mode,
                    use_ai,
                    preference,
                    include_readme,
                    github_client,
                    ai_client,
                    task_id,
                )
                async with counter_lock:
                    classified += batch_classified
                    failed += batch_failed
            except Exception:
                async with counter_lock:
                    failed += len(batch)
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await queue.join()
    await asyncio.gather(*workers)
    return (classified, failed)


def _clamp_concurrency(value: int) -> int:
    if value < 1:
        return 1
    if value > CLASSIFY_CONCURRENCY_MAX:
        return CLASSIFY_CONCURRENCY_MAX
    return value


def _clamp_batch_size(value: int) -> int:
    if value < 1:
        return 1
    if value > CLASSIFY_BATCH_SIZE_MAX:
        return CLASSIFY_BATCH_SIZE_MAX
    return value


async def _background_classify_loop(
    payload: BackgroundClassifyRequest,
    allow_fallback: bool,
    task_id: str,
) -> None:
    try:
        await _set_task_status(task_id, "running", started_at=_now_iso())
        current = get_settings()
        rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
        rules = load_rules(current.rules_json, fallback_path=rules_path)
        classify_mode, use_ai, warning = _resolve_classify_context(
            current,
            rules,
            allow_fallback,
        )
        if warning:
            logger.warning("Background classification: %s", warning)

        should_run = use_ai or (classify_mode != "ai_only" and bool(rules))
        if not should_run:
            await _update_classification_state(
                running=False,
                finished_at=datetime.now(timezone.utc).isoformat(),
                processed=0,
                failed=0,
                remaining=0,
                last_error=warning or "No classification sources available",
                batch_size=0,
                concurrency=0,
                task_id=task_id,
            )
            await _set_task_status(
                task_id,
                "failed",
                finished_at=_now_iso(),
                message=warning or "No classification sources available",
            )
            return

        data = load_taxonomy(current.ai_taxonomy_path)
        preference_user = _normalize_preference_user(payload.preference_user)
        preference = await get_user_preferences(preference_user)
        github_client: GitHubClient = app.state.github_client
        ai_client: AIClient = app.state.ai_client

        requested_batch_size = payload.limit if payload.limit and payload.limit > 0 else DEFAULT_CLASSIFY_BATCH_SIZE
        batch_size = _clamp_batch_size(requested_batch_size)
        concurrency_value = payload.concurrency if payload.concurrency and payload.concurrency > 0 else DEFAULT_CLASSIFY_CONCURRENCY
        concurrency = _clamp_concurrency(concurrency_value)
        force_mode = bool(payload.force)
        cursor_full_name = payload.cursor_full_name if force_mode else None
        total_force = None
        if force_mode:
            total_force = await count_repos_for_classification(True, cursor_full_name)
            remaining = total_force
        else:
            remaining = await count_repos_for_classification(False)

        await _update_classification_state(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            processed=0,
            failed=0,
            remaining=remaining,
            last_error=None,
            batch_size=batch_size,
            concurrency=concurrency,
            task_id=task_id,
        )

        success_total = 0
        processed_total = 0
        failed_total = 0
        remaining_refresh_every = max(1, CLASSIFY_REMAINING_REFRESH_EVERY)
        refresh_counter = 0
        while not classification_stop.is_set():
            if force_mode:
                repos_to_classify = await select_repos_for_classification(
                    batch_size,
                    True,
                    cursor_full_name,
                )
            else:
                repos_to_classify = await select_repos_for_classification(batch_size, False)
            if not repos_to_classify:
                break

            batch_classified, batch_failed = await _classify_repos_concurrent(
                repos_to_classify,
                data,
                rules,
                classify_mode,
                use_ai,
                preference,
                payload.include_readme,
                concurrency,
                github_client,
                ai_client,
                task_id,
            )
            processed = batch_classified + batch_failed
            success_total += batch_classified
            processed_total += processed
            failed_total += batch_failed
            if force_mode:
                last_repo = repos_to_classify[-1]
                if isinstance(last_repo, RepoBase):
                    cursor_full_name = last_repo.full_name
                else:
                    cursor_full_name = last_repo.get("full_name")
                remaining = max(0, (total_force or 0) - processed_total)
                if cursor_full_name:
                    await _set_task_status(
                        task_id,
                        "running",
                        cursor_full_name=cursor_full_name,
                    )
            else:
                # Reduce count query frequency - only refresh every N batches
                # Force refresh when failures occur to get accurate remaining count
                refresh_counter += 1
                should_refresh = (
                    refresh_counter % remaining_refresh_every == 0 or
                    batch_failed > 0  # Force refresh on failures for accuracy
                )
                if should_refresh:
                    remaining = await count_repos_for_classification(False)
                    refreshed = True
                else:
                    # Only decrement by successful classifications, not failures
                    remaining = max(0, remaining - batch_classified)
                    refreshed = False
            state = await _get_classification_state()
            await _update_classification_state(
                processed=state["processed"] + processed,
                failed=state["failed"] + batch_failed,
                remaining=remaining,
            )

            if processed == 0:
                break
            if CLASSIFY_BATCH_DELAY_MS > 0:
                await asyncio.sleep(CLASSIFY_BATCH_DELAY_MS / 1000)

        await _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            task_id=None,
        )
        await _set_task_status(
            task_id,
            "finished",
            finished_at=_now_iso(),
            result={"processed": processed_total, "classified": success_total, "failed": failed_total},
        )
        await cache.invalidate_prefix("stats")
        await cache.invalidate_prefix("repos")
    except Exception as exc:
        state = await _get_classification_state()
        await _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            processed=state.get("processed", 0),
            failed=state.get("failed", 0),
            remaining=state.get("remaining", 0),
            last_error=str(exc),
            batch_size=state.get("batch_size", 0),
            concurrency=state.get("concurrency", 0),
            task_id=None,
        )
        await _set_task_status(
            task_id,
            "failed",
            finished_at=_now_iso(),
            message=str(exc),
        )


@app.post("/classify", response_model=ClassifyResponse | TaskQueuedResponse, dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_HEAVY)
async def classify(request: Request, payload: ClassifyRequest) -> ClassifyResponse | TaskQueuedResponse:
    current = get_settings()
    try:
        data = load_taxonomy(current.ai_taxonomy_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.force:
        force_limit = 0 if payload.limit == 0 else _clamp_batch_size(payload.limit)
        task_id = str(uuid.uuid4())
        force_payload = BackgroundClassifyRequest(
            limit=force_limit,
            force=True,
            include_readme=payload.include_readme,
            preference_user=payload.preference_user,
            concurrency=DEFAULT_CLASSIFY_CONCURRENCY,
        )
        await _register_task(
            task_id,
            "classify",
            "Force classification queued",
            payload=force_payload.model_dump(),
        )
        started = await _start_background_classify(force_payload, task_id, allow_fallback=False)
        if not started:
            raise HTTPException(status_code=409, detail="Classification already running")
        response = TaskQueuedResponse(task_id=task_id, status="queued", message="Classification queued")
        return JSONResponse(status_code=202, content=response.model_dump())

    if payload.limit == 0:
        classify_limit = 0
    else:
        requested_limit = payload.limit if payload.limit > 0 else DEFAULT_CLASSIFY_BATCH_SIZE
        classify_limit = _clamp_batch_size(requested_limit)
    repos_to_classify = await select_repos_for_classification(classify_limit, payload.force)
    rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
    rules = load_rules(current.rules_json, fallback_path=rules_path)
    preference_user = _normalize_preference_user(payload.preference_user)
    preference = await get_user_preferences(preference_user)
    try:
        classify_mode, use_ai, warning = _resolve_classify_context(
            current,
            rules,
            allow_fallback=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if warning:
        logger.warning("Classification request: %s", warning)

    github_client: GitHubClient = app.state.github_client
    ai_client: AIClient = app.state.ai_client
    classified, failed = await _classify_repos_concurrent(
        repos_to_classify,
        data,
        rules,
        classify_mode,
        use_ai,
        preference,
        payload.include_readme,
        concurrency=1,
        github_client=github_client,
        ai_client=ai_client,
        task_id=None,
    )

    if repos_to_classify:
        await cache.invalidate_prefix("stats")
        await cache.invalidate_prefix("repos")

    return ClassifyResponse(
        total=len(repos_to_classify),
        classified=classified,
        failed=failed,
        remaining_unclassified=await count_unclassified_repos(),
    )


@app.post(
    "/classify/background",
    response_model=BackgroundClassifyResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
@limiter.limit(RATE_LIMIT_HEAVY)
async def classify_background(request: Request, payload: BackgroundClassifyRequest) -> BackgroundClassifyResponse:
    task_id = str(uuid.uuid4())
    await _register_task(
        task_id,
        "classify",
        "Background classification queued",
        payload=payload.model_dump(),
    )
    started = await _start_background_classify(payload, task_id, allow_fallback=False)
    if not started:
        raise HTTPException(status_code=409, detail="Classification already running")

    return BackgroundClassifyResponse(
        started=True,
        running=True,
        message="Background classification started",
        task_id=task_id,
    )


@app.get("/classify/status", response_model=BackgroundClassifyStatusResponse)
async def classify_status() -> BackgroundClassifyStatusResponse:
    state = await _get_classification_state()
    if not state.get("running"):
        state["task_id"] = None
    return BackgroundClassifyStatusResponse(**state)


@app.post("/classify/stop", dependencies=[Depends(require_admin)])
async def classify_stop() -> dict:
    classification_stop.set()
    await _update_classification_state(last_error="Stopped by user")
    return {"stopped": True}


@app.get("/metrics/quality")
async def quality_metrics_endpoint() -> dict:
    return await _get_quality_metrics()


@app.get("/stats", response_model=StatsResponse)
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


@app.get("/api/config/client-settings", response_model=ClientSettingsResponse)
async def client_settings() -> ClientSettingsResponse:
    current = get_settings()
    rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
    rules = load_rules(current.rules_json, fallback_path=rules_path)
    try:
        _resolve_classify_context(current, rules, allow_fallback=False)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Server configuration error: {exc}. Check server .env settings.",
        ) from exc
    return ClientSettingsResponse(
        github_mode=current.github_mode,
        classify_mode=current.classify_mode,
        auto_classify_after_sync=current.auto_classify_after_sync,
    )


@app.get("/settings", response_model=SettingsResponse)
async def settings() -> SettingsResponse:
    current = get_settings()
    return SettingsResponse(
        github_username=current.github_username,
        github_target_username=current.github_target_username,
        github_usernames=current.github_usernames,
        github_include_self=current.github_include_self,
        github_mode=current.github_mode,
        classify_mode=current.classify_mode,
        auto_classify_after_sync=current.auto_classify_after_sync,
        rules_json=current.rules_json,
        sync_cron=current.sync_cron,
        sync_timeout=current.sync_timeout,
        github_token_set=bool(os.getenv("GITHUB_TOKEN")),
        ai_api_key_set=bool(os.getenv("AI_API_KEY")),
    )


@app.patch("/settings", response_model=SettingsResponse, dependencies=[Depends(require_admin)])
async def update_settings(payload: SettingsRequest) -> SettingsResponse:
    fields = payload.model_fields_set
    updates: Dict[str, Optional[object]] = {}

    for field in fields:
        updates[field.upper()] = getattr(payload, field)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    await asyncio.to_thread(write_settings, updates)
    current = get_settings()
    return SettingsResponse(
        github_username=current.github_username,
        github_target_username=current.github_target_username,
        github_usernames=current.github_usernames,
        github_include_self=current.github_include_self,
        github_mode=current.github_mode,
        classify_mode=current.classify_mode,
        auto_classify_after_sync=current.auto_classify_after_sync,
        rules_json=current.rules_json,
        sync_cron=current.sync_cron,
        sync_timeout=current.sync_timeout,
        github_token_set=bool(os.getenv("GITHUB_TOKEN")),
        ai_api_key_set=bool(os.getenv("AI_API_KEY")),
    )
