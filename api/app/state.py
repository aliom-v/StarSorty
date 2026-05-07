import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("starsorty.api")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r, fallback to %s", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("Out-of-range %s=%r, fallback to %s", name, raw, default)
        return default
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r, fallback to %s", name, raw, default)
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


# ---------------------------------------------------------------------------
# Environment-derived constants
# ---------------------------------------------------------------------------

API_SEMAPHORE_LIMIT = _env_int("API_SEMAPHORE_LIMIT", 5, minimum=1)
TASK_STALE_MINUTES = _env_int("TASK_STALE_MINUTES", 10, minimum=1)
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
CLASSIFY_README_DESCRIPTION_MIN_CHARS = _env_int(
    "CLASSIFY_README_DESCRIPTION_MIN_CHARS",
    120,
    minimum=0,
)
CLASSIFY_README_MIN_TOPICS = _env_int("CLASSIFY_README_MIN_TOPICS", 2, minimum=0)
RULE_DIRECT_THRESHOLD = _env_float("RULE_DIRECT_THRESHOLD", 0.88, minimum=0.0, maximum=1.0)
RULE_AI_THRESHOLD = _env_float("RULE_AI_THRESHOLD", 0.45, minimum=0.0, maximum=1.0)
RULE_MIN_THRESHOLD = _env_float("RULE_MIN_THRESHOLD", 0.42, minimum=0.0, maximum=1.0)
RULE_AMBIGUITY_GAP = _env_float("RULE_AMBIGUITY_GAP", 0.08, minimum=0.0, maximum=1.0)


# ---------------------------------------------------------------------------
# Classification global state
# ---------------------------------------------------------------------------

CLASSIFICATION_STATE_KEY = "classification_state"
CLASSIFICATION_CONTROL_KEY = "classification_control"

CLASSIFICATION_STATE_DEFAULTS = {
    "status": "idle",
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

QUALITY_METRIC_DEFAULTS = {
    "classification_total": 0,
    "rule_hit_total": 0,
    "ai_fallback_total": 0,
    "empty_tag_total": 0,
    "uncategorized_total": 0,
    "search_total": 0,
    "search_zero_result_total": 0,
    "api_request_total": 0,
    "api_error_total": 0,
    "api_request_latency_ms_total": 0,
    "task_queued_total": 0,
    "task_finished_total": 0,
    "task_failed_total": 0,
    "task_stopped_total": 0,
    "cache_hit_total": 0,
    "cache_miss_total": 0,
    "db_lock_conflict_total": 0,
    "db_lock_retry_total": 0,
    "db_lock_retry_exhausted_total": 0,
}

classification_lock = asyncio.Lock()
classification_stop = asyncio.Event()
classification_task: asyncio.Task | None = None
classification_state = dict(CLASSIFICATION_STATE_DEFAULTS)
classification_control = {"stop_requested": False}

quality_metrics_lock = asyncio.Lock()
quality_metrics = dict(QUALITY_METRIC_DEFAULTS)


# ---------------------------------------------------------------------------
# State accessor helpers
# ---------------------------------------------------------------------------

def _normalize_classification_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(CLASSIFICATION_STATE_DEFAULTS)
    if not isinstance(payload, dict):
        return data
    for key in data:
        if key not in payload:
            continue
        value = payload.get(key)
        if key in ("processed", "failed", "remaining", "batch_size", "concurrency"):
            try:
                data[key] = int(value or 0)
            except (TypeError, ValueError):
                data[key] = CLASSIFICATION_STATE_DEFAULTS[key]
        elif key == "running":
            data[key] = bool(value)
        else:
            data[key] = value
    return data


def _normalize_quality_metrics(payload: dict[str, Any] | None) -> dict[str, int]:
    data = dict(QUALITY_METRIC_DEFAULTS)
    if not isinstance(payload, dict):
        return data
    for key in data:
        if key not in payload:
            continue
        try:
            data[key] = int(payload.get(key) or 0)
        except (TypeError, ValueError):
            data[key] = QUALITY_METRIC_DEFAULTS[key]
    return data


def _derive_quality_metrics(data: dict[str, int]) -> dict[str, float | int]:
    derived: dict[str, float | int] = dict(data)
    classification_total = max(1, int(data.get("classification_total", 0)))
    search_total = max(1, int(data.get("search_total", 0)))
    api_request_total = max(1, int(data.get("api_request_total", 0)))
    task_queued_total = max(1, int(data.get("task_queued_total", 0)))
    cache_total = max(
        1,
        int(data.get("cache_hit_total", 0)) + int(data.get("cache_miss_total", 0)),
    )
    derived["rule_hit_rate"] = data.get("rule_hit_total", 0) / classification_total
    derived["ai_fallback_rate"] = data.get("ai_fallback_total", 0) / classification_total
    derived["empty_tag_rate"] = data.get("empty_tag_total", 0) / classification_total
    derived["uncategorized_rate"] = data.get("uncategorized_total", 0) / classification_total
    derived["search_zero_result_rate"] = data.get("search_zero_result_total", 0) / search_total
    derived["api_error_rate"] = data.get("api_error_total", 0) / api_request_total
    derived["api_request_latency_ms_avg"] = (
        data.get("api_request_latency_ms_total", 0) / api_request_total
    )
    derived["task_failure_rate"] = data.get("task_failed_total", 0) / task_queued_total
    derived["cache_hit_rate"] = data.get("cache_hit_total", 0) / cache_total
    return derived


async def _load_runtime_state_payload(state_key: str) -> dict[str, Any] | None:
    try:
        from .runtime_store import load_runtime_state

        return await load_runtime_state(state_key)
    except Exception:
        logger.debug("Failed to load runtime state for %s", state_key, exc_info=True)
        return None


async def _store_runtime_state_payload(state_key: str, payload: dict[str, Any]) -> None:
    try:
        from .runtime_store import store_runtime_state

        await store_runtime_state(state_key, payload)
    except Exception:
        logger.debug("Failed to persist runtime state for %s", state_key, exc_info=True)


async def _load_runtime_metrics_payload() -> dict[str, int] | None:
    try:
        from .runtime_store import get_runtime_metrics

        return await get_runtime_metrics()
    except Exception:
        logger.debug("Failed to load runtime metrics", exc_info=True)
        return None


async def _add_runtime_metrics_delta(delta: dict[str, int]) -> None:
    try:
        from .runtime_store import add_runtime_metrics

        await add_runtime_metrics(delta)
    except Exception:
        logger.debug("Failed to persist runtime metrics", exc_info=True)


async def _set_classification_state_snapshot(snapshot: dict[str, Any]) -> None:
    normalized = _normalize_classification_state(snapshot)
    async with classification_lock:
        classification_state.clear()
        classification_state.update(normalized)
    await _store_runtime_state_payload(CLASSIFICATION_STATE_KEY, normalized)


async def _update_classification_state(**updates: object) -> None:
    async with classification_lock:
        classification_state.update(updates)
        snapshot = dict(classification_state)
    await _store_runtime_state_payload(
        CLASSIFICATION_STATE_KEY,
        _normalize_classification_state(snapshot),
    )


async def _get_classification_state() -> dict:
    payload = await _load_runtime_state_payload(CLASSIFICATION_STATE_KEY)
    if payload is not None:
        normalized = _normalize_classification_state(payload)
        async with classification_lock:
            classification_state.clear()
            classification_state.update(normalized)
            return dict(classification_state)
    async with classification_lock:
        return dict(classification_state)


async def _set_classification_stop_requested(requested: bool) -> None:
    async with classification_lock:
        classification_control["stop_requested"] = bool(requested)
    if requested:
        classification_stop.set()
    else:
        classification_stop.clear()
    await _store_runtime_state_payload(
        CLASSIFICATION_CONTROL_KEY,
        {"stop_requested": bool(requested)},
    )


async def _is_classification_stop_requested() -> bool:
    payload = await _load_runtime_state_payload(CLASSIFICATION_CONTROL_KEY)
    if payload is not None:
        requested = bool(payload.get("stop_requested"))
        async with classification_lock:
            classification_control["stop_requested"] = requested
        return requested
    async with classification_lock:
        return bool(classification_control.get("stop_requested"))


async def _add_quality_metrics(**delta: int) -> None:
    normalized = {
        key: int(value or 0)
        for key, value in delta.items()
        if key in QUALITY_METRIC_DEFAULTS and int(value or 0) != 0
    }
    if not normalized:
        return
    async with quality_metrics_lock:
        for key, value in normalized.items():
            quality_metrics[key] = int(quality_metrics.get(key, 0) or 0) + value
    await _add_runtime_metrics_delta(normalized)


async def _get_quality_metrics() -> dict:
    payload = await _load_runtime_metrics_payload()
    if payload is not None:
        normalized = _normalize_quality_metrics(payload)
        async with quality_metrics_lock:
            quality_metrics.clear()
            quality_metrics.update(normalized)
            data = dict(quality_metrics)
        return _derive_quality_metrics(data)
    async with quality_metrics_lock:
        data = dict(quality_metrics)
    return _derive_quality_metrics(data)


async def initialize_runtime_state() -> None:
    state_payload = await _load_runtime_state_payload(CLASSIFICATION_STATE_KEY)
    control_payload = await _load_runtime_state_payload(CLASSIFICATION_CONTROL_KEY)
    metrics_payload = await _load_runtime_metrics_payload()

    async with classification_lock:
        classification_state.clear()
        classification_state.update(_normalize_classification_state(state_payload))
        classification_control["stop_requested"] = bool(
            (control_payload or {}).get("stop_requested")
        )
        if classification_control["stop_requested"]:
            classification_stop.set()
        else:
            classification_stop.clear()

    async with quality_metrics_lock:
        quality_metrics.clear()
        quality_metrics.update(_normalize_quality_metrics(metrics_payload))

    try:
        from .db import get_active_task
    except Exception:
        return

    active_task = await get_active_task("classify")
    if active_task:
        return

    stale_running = False
    stale_stop_requested = False
    async with classification_lock:
        stale_running = bool(
            classification_state.get("running")
            or classification_state.get("status") in ("queued", "running")
        )
        stale_stop_requested = bool(classification_control.get("stop_requested"))

    if stale_running:
        await _set_classification_state_snapshot(CLASSIFICATION_STATE_DEFAULTS)
    if stale_stop_requested:
        await _set_classification_stop_requested(False)
    classification_stop.clear()
