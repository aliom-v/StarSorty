import logging
import uuid

from fastapi import APIRouter, Depends, Request

from ..cache import cache
from ..config import get_settings
from ..db import (
    get_active_task,
    get_sync_status,
    prune_star_user,
    prune_users_not_in,
    update_sync_status,
    upsert_repos,
)
from ..deps import (
    _handle_task_exception,
    _now_iso,
    _register_task,
    _register_task_if_available,
    _set_task_status,
    require_admin,
)
from ..github import GitHubClient
from ..observability import create_observed_task
from ..rate_limit import limiter, RATE_LIMIT_HEAVY
from ..schemas import (
    BackgroundClassifyRequest,
    StatusResponse,
    TaskQueuedResponse,
)
from ..state import DEFAULT_CLASSIFY_BATCH_SIZE, DEFAULT_CLASSIFY_CONCURRENCY

logger = logging.getLogger("starsorty.api")

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    status_data = await get_sync_status()
    return StatusResponse(**status_data)


async def _run_sync_task(task_id: str, app_state: object) -> None:
    from .classify import _queue_background_classify_task

    await _set_task_status(task_id, "running", started_at=_now_iso())
    current = get_settings()
    github_client: GitHubClient = app_state.github_client

    try:
        targets = await github_client.resolve_targets()
    except Exception as exc:
        logger.exception("Sync target resolution failed")
        await update_sync_status("error", str(exc))
        await _set_task_status(task_id, "failed", finished_at=_now_iso(), message=str(exc))
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
        logger.exception("Sync repository refresh failed")
        await update_sync_status("error", str(exc))
        await _set_task_status(task_id, "failed", finished_at=_now_iso(), message=str(exc))
        return

    await _set_task_status(
        task_id,
        "finished",
        finished_at=_now_iso(),
        result={"count": total, "queued_at": timestamp},
    )

    await cache.invalidate_prefix("repos")

    if current.auto_classify_after_sync:
        auto_payload = BackgroundClassifyRequest(
            limit=DEFAULT_CLASSIFY_BATCH_SIZE,
            force=False,
            include_readme=True,
            concurrency=DEFAULT_CLASSIFY_CONCURRENCY,
        )
        classify_task_id = await _queue_background_classify_task(
            auto_payload,
            message="Auto classify after sync",
            allow_fallback=True,
        )
        if classify_task_id is None:
            logger.info("Auto classify skipped because classification is already running")


@router.post("/sync", response_model=TaskQueuedResponse, status_code=202, dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_HEAVY)
async def sync(request: Request) -> TaskQueuedResponse:
    task_id = str(uuid.uuid4())
    created = await _register_task_if_available(task_id, "sync", payload={})
    if not created:
        existing = await get_active_task("sync")
        if existing:
            return TaskQueuedResponse(
                task_id=existing["task_id"],
                status=str(existing.get("status") or "running"),
                message="Sync already running",
            )
        await _register_task(task_id, "sync", payload={})
    bg_task = create_observed_task(
        _run_sync_task(task_id, request.app.state),
        task_id=task_id,
        name=f"sync:{task_id}",
    )
    bg_task.add_done_callback(_handle_task_exception)
    return TaskQueuedResponse(task_id=task_id, status="queued", message="Sync queued")
