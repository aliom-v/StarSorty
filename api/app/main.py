import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_settings
from .db import (
    count_unclassified_repos,
    count_repos_for_classification,
    create_task,
    get_repo_stats,
    get_repo,
    get_task,
    get_sync_status,
    get_failed_repos,
    increment_classify_fail_count,
    init_db,
    init_db_pool,
    close_db_pool,
    list_override_history,
    list_repos,
    prune_star_user,
    prune_users_not_in,
    record_readme_fetch,
    record_readme_fetches,
    reset_classify_fail_count,
    reset_stale_tasks,
    select_repos_for_classification,
    update_task,
    update_classification,
    update_classifications_bulk,
    update_override,
    update_sync_status,
    upsert_repos,
)
from .github import GitHubClient
from .models import RepoBase
from .ai_client import AIClient
from .taxonomy import load_taxonomy, validate_classification
from .rules import load_rules, match_rule
from .settings_store import write_settings
import httpx
import uuid

API_SEMAPHORE_LIMIT = int(os.getenv("API_SEMAPHORE_LIMIT", "5"))
TASK_STALE_MINUTES = int(os.getenv("TASK_STALE_MINUTES", "10"))


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
        await github_http.aclose()
        await ai_http.aclose()
        await close_db_pool()


app = FastAPI(title="StarSorty API", version="0.1.0", lifespan=lifespan)
logger = logging.getLogger("starsorty.api")
DEFAULT_CLASSIFY_BATCH_SIZE = int(os.getenv("CLASSIFY_BATCH_SIZE", "50"))
DEFAULT_CLASSIFY_CONCURRENCY = int(os.getenv("CLASSIFY_CONCURRENCY", "3"))
CLASSIFY_CONCURRENCY_MAX = int(os.getenv("CLASSIFY_CONCURRENCY_MAX", "10"))
CLASSIFY_BATCH_DELAY_MS = int(os.getenv("CLASSIFY_BATCH_DELAY_MS", "0"))
AI_CLASSIFY_BATCH_SIZE = int(os.getenv("AI_CLASSIFY_BATCH_SIZE", "5"))
CLASSIFY_REMAINING_REFRESH_EVERY = int(os.getenv("CLASSIFY_REMAINING_REFRESH_EVERY", "5"))
AI_BATCH_FALLBACK = (
    os.getenv("AI_BATCH_FALLBACK", "1").strip().lower()
    not in ("0", "false", "no")
)

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


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    if not admin_token:
        return
    if x_admin_token != admin_token:
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
    ai_category: str | None
    ai_subcategory: str | None
    ai_confidence: float | None
    ai_tags: List[str]
    ai_keywords: List[str]
    ai_provider: str | None
    ai_model: str | None
    ai_updated_at: str | None
    override_category: str | None
    override_subcategory: str | None
    override_tags: List[str]
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


class RepoListResponse(BaseModel):
    total: int
    items: List[RepoOut]


class OverrideRequest(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
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
    limit: int = 20
    force: bool = False
    include_readme: bool = True


class ClassifyResponse(BaseModel):
    total: int
    classified: int
    failed: int
    remaining_unclassified: int


class BackgroundClassifyRequest(ClassifyRequest):
    concurrency: Optional[int] = None
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


class ReadmeResponse(BaseModel):
    updated: bool
    summary: str


class TaxonomyCategory(BaseModel):
    name: str
    subcategories: List[str] = []


class TaxonomyResponse(BaseModel):
    categories: List[TaxonomyCategory]
    tags: List[str]


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
    sync_timeout: Optional[int] = None


class ClientSettingsResponse(BaseModel):
    github_mode: str
    classify_mode: str
    auto_classify_after_sync: bool


class StatsItem(BaseModel):
    name: str
    count: int


class StatsResponse(BaseModel):
    total: int
    unclassified: int
    categories: List[StatsItem]
    tags: List[StatsItem]
    users: List[StatsItem]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
async def auth_check() -> dict:
    return {"ok": True}


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def task_status(task_id: str) -> TaskStatusResponse:
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
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


@app.post("/sync", response_model=TaskQueuedResponse, status_code=202, dependencies=[Depends(require_admin)])
async def sync() -> TaskQueuedResponse:
    task_id = str(uuid.uuid4())
    await _register_task(task_id, "sync", payload={})
    asyncio.create_task(_run_sync_task(task_id))
    return TaskQueuedResponse(task_id=task_id, status="queued", message="Sync queued")


@app.get("/repos", response_model=RepoListResponse)
async def repos(
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[str] = None,
    star_user: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> RepoListResponse:
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    total, items = await list_repos(
        q=q,
        language=language,
        min_stars=min_stars,
        category=category,
        subcategory=subcategory,
        tag=tag,
        tags=tag_list,
        star_user=star_user,
        limit=limit,
        offset=offset,
    )
    items_out = [RepoOut(**item.model_dump()) if isinstance(item, RepoBase) else RepoOut(**item) for item in items]
    return RepoListResponse(total=total, items=items_out)


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
    if "note" in fields:
        if payload.note is not None and not str(payload.note).strip():
            raise HTTPException(status_code=400, detail="note cannot be empty")
        updates["note"] = payload.note

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    updated = await update_override(full_name, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Repo not found or no updates")
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
    return ReadmeResponse(updated=bool(summary), summary=summary)


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
async def list_failed_repos(min_fail_count: int = 5) -> FailedReposResponse:
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


@app.get("/taxonomy", response_model=TaxonomyResponse)
async def taxonomy() -> TaxonomyResponse:
    current = get_settings()
    data = load_taxonomy(current.ai_taxonomy_path)
    return TaxonomyResponse(categories=data.get("categories", []), tags=data.get("tags", []))


async def _update_classification_state(**updates: object) -> None:
    async with classification_lock:
        classification_state.update(updates)


async def _get_classification_state() -> dict:
    async with classification_lock:
        return dict(classification_state)


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
    use_rules = classify_mode != "ai_only"
    if use_rules:
        rule = match_rule(repo_data, rules)
        if rule:
            validated = validate_classification(
                {
                    "category": rule.get("category"),
                    "subcategory": rule.get("subcategory"),
                    "tags": rule.get("tags") or [],
                    "confidence": 1.0,
                },
                data,
            )
            await update_classification(
                repo_data["full_name"],
                validated["category"],
                validated["subcategory"],
                validated["confidence"],
                validated["tags"],
                "rules",
                "rules",
            )
            return True
    if not use_ai:
        return False
    result = await ai_client.classify_repo_with_retry(repo_data, data, retries=2)
    await update_classification(
        repo_data["full_name"],
        result["category"],
        result["subcategory"],
        result["confidence"],
        result["tags"],
        result["provider"],
        result["model"],
        summary_zh=result.get("summary_zh"),
        keywords=result.get("keywords"),
    )
    return True


async def _classify_repos_batch(
    repos: list,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    include_readme: bool,
    github_client: GitHubClient,
    ai_client: AIClient,
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

    use_rules = classify_mode != "ai_only"
    pending_ai: list[dict] = []
    rule_updates: list[dict] = []

    for repo_data in repo_datas:
        if use_rules:
            rule = match_rule(repo_data, rules)
            if rule:
                validated = validate_classification(
                    {
                        "category": rule.get("category"),
                        "subcategory": rule.get("subcategory"),
                        "tags": rule.get("tags") or [],
                        "confidence": 1.0,
                    },
                    data,
                )
                rule_updates.append(
                    {
                        "full_name": repo_data.get("full_name"),
                        "category": validated["category"],
                        "subcategory": validated["subcategory"],
                        "confidence": validated["confidence"],
                        "tags": validated["tags"],
                        "provider": "rules",
                        "model": "rules",
                    }
                )
                continue
        if use_ai:
            pending_ai.append(repo_data)
        else:
            failed += 1

    # Bulk write rule classifications
    if rule_updates:
        try:
            await update_classifications_bulk(rule_updates)
            classified += len(rule_updates)
            for item in rule_updates:
                if item.get("full_name"):
                    success_full_names.add(item["full_name"])
        except Exception as exc:
            logger.warning("Bulk rule classification update failed: %s", exc)
            for item in rule_updates:
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
                        item["provider"],
                        item["model"],
                    )
                    classified += 1
                    success_full_names.add(full_name)
                except Exception:
                    failed += 1

    # AI classification with fallback
    if pending_ai:
        ai_updates: list[dict] = []
        fallback_targets: list[dict] = []
        batch_error: Exception | None = None
        try:
            results = await ai_client.classify_repos_with_retry(pending_ai, data, retries=2)
        except Exception as exc:
            batch_error = exc
            results = [None for _ in pending_ai]

        for repo_data, result in zip(pending_ai, results):
            if result:
                ai_updates.append(
                    {
                        "full_name": repo_data.get("full_name"),
                        "category": result["category"],
                        "subcategory": result["subcategory"],
                        "confidence": result["confidence"],
                        "tags": result["tags"],
                        "provider": result["provider"],
                        "model": result["model"],
                        "summary_zh": result.get("summary_zh"),
                        "keywords": result.get("keywords"),
                    }
                )
            else:
                fallback_targets.append(repo_data)

        # Fallback: retry failed items individually
        if fallback_targets:
            if AI_BATCH_FALLBACK:
                if batch_error:
                    logger.warning(
                        "AI batch classify failed, falling back to single-repo requests: %s",
                        batch_error,
                    )
                fallback_results = await asyncio.gather(
                    *(
                        ai_client.classify_repo_with_retry(repo_data, data, retries=1)
                        for repo_data in fallback_targets
                    ),
                    return_exceptions=True,
                )
                for repo_data, result in zip(fallback_targets, fallback_results):
                    if isinstance(result, Exception) or not result:
                        failed += 1
                        continue
                    ai_updates.append(
                        {
                            "full_name": repo_data.get("full_name"),
                            "category": result["category"],
                            "subcategory": result["subcategory"],
                            "confidence": result["confidence"],
                            "tags": result["tags"],
                            "provider": result["provider"],
                            "model": result["model"],
                            "summary_zh": result.get("summary_zh"),
                            "keywords": result.get("keywords"),
                        }
                    )
            else:
                if batch_error:
                    logger.warning("AI batch classify failed: %s", batch_error)
                failed += len(fallback_targets)

        # Bulk write AI classifications
        if ai_updates:
            try:
                await update_classifications_bulk(ai_updates)
                classified += len(ai_updates)
                for item in ai_updates:
                    if item.get("full_name"):
                        success_full_names.add(item["full_name"])
            except Exception as exc:
                logger.warning("Bulk AI classification update failed: %s", exc)
                for item in ai_updates:
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
                            item["provider"],
                            item["model"],
                            summary_zh=item.get("summary_zh"),
                            keywords=item.get("keywords"),
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

    return (classified, failed)


async def _classify_repos_concurrent(
    repos_to_classify: list,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    include_readme: bool,
    concurrency: int,
    github_client: GitHubClient,
    ai_client: AIClient,
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
                    include_readme,
                    github_client,
                    ai_client,
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
                    include_readme,
                    github_client,
                    ai_client,
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
        github_client: GitHubClient = app.state.github_client
        ai_client: AIClient = app.state.ai_client

        batch_size = payload.limit if payload.limit and payload.limit > 0 else DEFAULT_CLASSIFY_BATCH_SIZE
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

        previous_remaining = None
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
                payload.include_readme,
                concurrency,
                github_client,
                ai_client,
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
            if not force_mode:
                # Check for no progress on refresh (includes after failures)
                if refreshed:
                    if previous_remaining is not None and remaining >= previous_remaining:
                        break
                    previous_remaining = remaining
            if CLASSIFY_BATCH_DELAY_MS > 0:
                await asyncio.sleep(CLASSIFY_BATCH_DELAY_MS / 1000)

        await _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            task_id=task_id,
        )
        await _set_task_status(
            task_id,
            "finished",
            finished_at=_now_iso(),
            result={"processed": processed_total, "classified": success_total, "failed": failed_total},
        )
    except Exception as exc:
        await _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            processed=0,
            failed=0,
            remaining=0,
            last_error=str(exc),
            batch_size=0,
            concurrency=0,
            task_id=task_id,
        )
        await _set_task_status(
            task_id,
            "failed",
            finished_at=_now_iso(),
            message=str(exc),
        )


@app.post("/classify", response_model=ClassifyResponse | TaskQueuedResponse, dependencies=[Depends(require_admin)])
async def classify(payload: ClassifyRequest) -> ClassifyResponse | TaskQueuedResponse:
    current = get_settings()
    try:
        data = load_taxonomy(current.ai_taxonomy_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.force:
        task_id = str(uuid.uuid4())
        force_payload = BackgroundClassifyRequest(
            limit=payload.limit,
            force=True,
            include_readme=payload.include_readme,
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

    repos_to_classify = await select_repos_for_classification(payload.limit, payload.force)
    rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
    rules = load_rules(current.rules_json, fallback_path=rules_path)
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
        payload.include_readme,
        concurrency=1,
        github_client=github_client,
        ai_client=ai_client,
    )

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
async def classify_background(payload: BackgroundClassifyRequest) -> BackgroundClassifyResponse:
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
    return BackgroundClassifyStatusResponse(**state)


@app.post("/classify/stop", dependencies=[Depends(require_admin)])
async def classify_stop() -> dict:
    classification_stop.set()
    await _update_classification_state(last_error="Stopped by user")
    return {"stopped": True}


@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    data = await get_repo_stats()
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
