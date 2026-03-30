import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import Cookie, Header, HTTPException, Request

from .db import create_task, create_task_if_available, get_admin_session, update_task
from .observability import bind_log_context
from .security import (
    ADMIN_SESSION_COOKIE_NAME,
    admin_request_requires_csrf,
    allow_unauthenticated_admin_in_dev,
    get_admin_token,
)
from .state import _add_quality_metrics

logger = logging.getLogger("starsorty.api")

_admin_token_warned = False


def _admin_auth_failure_exception() -> HTTPException:
    if get_admin_token():
        return HTTPException(status_code=401, detail="Admin authentication required")
    return HTTPException(
        status_code=503,
        detail=(
            "Admin endpoints are disabled because ADMIN_TOKEN is not configured. "
            "Set ADMIN_TOKEN, or enable ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV=1 for local development only."
        ),
    )


async def _resolve_admin_session_auth(
    request: Request,
    *,
    admin_session: str | None,
    x_csrf_token: str | None,
) -> str | None:
    if not admin_session:
        return None
    session = await get_admin_session(admin_session)
    if not session:
        return None
    if admin_request_requires_csrf(request.method):
        if not x_csrf_token:
            return None
        if not secrets.compare_digest(x_csrf_token, session["csrf_token"]):
            return None
    return "session"


async def resolve_admin_auth_mode(
    request: Request,
    x_admin_token: str | None = None,
    x_csrf_token: str | None = None,
    admin_session: str | None = None,
) -> str | None:
    global _admin_token_warned
    admin_token = get_admin_token()
    if admin_token:
        if x_admin_token and secrets.compare_digest(x_admin_token, admin_token):
            return "token"
        return await _resolve_admin_session_auth(
            request,
            admin_session=admin_session,
            x_csrf_token=x_csrf_token,
        )
    if allow_unauthenticated_admin_in_dev():
        if not _admin_token_warned:
            logger.warning(
                "ADMIN_TOKEN is not set, but admin endpoints remain enabled because "
                "ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV is active outside production."
            )
            _admin_token_warned = True
        return "dev_override"
    return None


async def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    admin_session: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
) -> None:
    auth_mode = await resolve_admin_auth_mode(
        request,
        x_admin_token=x_admin_token,
        x_csrf_token=x_csrf_token,
        admin_session=admin_session,
    )
    if auth_mode is not None:
        return
    raise _admin_auth_failure_exception()


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


async def _register_task_if_available(
    task_id: str,
    task_type: str,
    message: str | None = None,
    payload: dict | None = None,
    retry_from_task_id: str | None = None,
) -> bool:
    with bind_log_context(task_id=task_id):
        created = await create_task_if_available(
            task_id,
            task_type,
            status="queued",
            message=message,
            payload=payload,
            retry_from_task_id=retry_from_task_id,
        )
        if not created:
            return False
        await _add_quality_metrics(task_queued_total=1)
        logger.info(
            "task_registered type=%s status=queued retry_from=%s",
            task_type,
            retry_from_task_id or "-",
        )
        return True


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
        elif status == "stopped":
            await _add_quality_metrics(task_stopped_total=1)

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
