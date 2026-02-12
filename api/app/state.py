import asyncio
import logging
import os

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
RULE_DIRECT_THRESHOLD = _env_float("RULE_DIRECT_THRESHOLD", 0.88, minimum=0.0, maximum=1.0)
RULE_AI_THRESHOLD = _env_float("RULE_AI_THRESHOLD", 0.45, minimum=0.0, maximum=1.0)


# ---------------------------------------------------------------------------
# Classification global state
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# State accessor helpers
# ---------------------------------------------------------------------------

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
