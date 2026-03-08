import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Header, HTTPException

from .db import create_task, update_task
from .observability import bind_log_context
from .security import get_admin_token
from .state import _add_quality_metrics

logger = logging.getLogger("starsorty.api")

_admin_token_warned = False


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    global _admin_token_warned
    admin_token = get_admin_token()
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_preference_user(value: Optional[str]) -> str:
    normalized = str(value or "global").strip()
    return normalized or "global"


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


def _handle_task_exception(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
        if exc is not None:
            with bind_log_context(
                request_id=getattr(task, "_starsorty_request_id", None),
                task_id=getattr(task, "_starsorty_task_id", None),
            ):
                logger.error("Background task failed: %s", exc, exc_info=exc)
    except asyncio.CancelledError:
        pass


async def _register_task(
    task_id: str,
    task_type: str,
    message: str | None = None,
    payload: dict | None = None,
    retry_from_task_id: str | None = None,
) -> None:
    with bind_log_context(task_id=task_id):
        await create_task(
            task_id,
            task_type,
            status="queued",
            message=message,
            payload=payload,
            retry_from_task_id=retry_from_task_id,
        )
        await _add_quality_metrics(task_queued_total=1)
        logger.info(
            "task_registered type=%s status=queued retry_from=%s",
            task_type,
            retry_from_task_id or "-",
        )


async def _set_task_status(task_id: str, status: str, **updates: object) -> None:
    with bind_log_context(task_id=task_id):
        await update_task(
            task_id,
            status,
            started_at=updates.get("started_at"),
            finished_at=updates.get("finished_at"),
            message=updates.get("message"),
            result=updates.get("result"),
            cursor_full_name=updates.get("cursor_full_name"),
        )
        if status == "finished":
            await _add_quality_metrics(task_finished_total=1)
        elif status == "failed":
            await _add_quality_metrics(task_failed_total=1)

        should_log = (
            status != "running"
            or updates.get("started_at") is not None
            or updates.get("message") is not None
        )
        if should_log:
            log_fn = logger.warning if status == "failed" else logger.info
            log_fn(
                "task_status_updated status=%s message=%s",
                status,
                updates.get("message") or "-",
            )
