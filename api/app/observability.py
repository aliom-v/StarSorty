import asyncio
import contextvars
import logging
import uuid
from contextlib import contextmanager
from typing import Awaitable, Iterator, TypeVar

REQUEST_ID_HEADER = "X-Request-ID"

_UNSET = object()
_T = TypeVar("_T")
_BASE_LOG_RECORD_FACTORY = logging.getLogRecordFactory()
_request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "starsorty_request_id",
    default=None,
)
_task_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "starsorty_task_id",
    default=None,
)
_log_record_factory_configured = False


def _normalize_context_id(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:128]


def resolve_request_id(value: str | None = None) -> str:
    normalized = _normalize_context_id(value)
    return normalized or str(uuid.uuid4())


def get_request_id() -> str | None:
    return _request_id_context.get()


def get_task_id() -> str | None:
    return _task_id_context.get()


@contextmanager
def bind_log_context(
    *,
    request_id: object = _UNSET,
    task_id: object = _UNSET,
) -> Iterator[None]:
    request_token: contextvars.Token[str | None] | None = None
    task_token: contextvars.Token[str | None] | None = None
    if request_id is not _UNSET:
        request_token = _request_id_context.set(_normalize_context_id(request_id))
    if task_id is not _UNSET:
        task_token = _task_id_context.set(_normalize_context_id(task_id))
    try:
        yield
    finally:
        if task_token is not None:
            _task_id_context.reset(task_token)
        if request_token is not None:
            _request_id_context.reset(request_token)


def _context_log_record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
    record = _BASE_LOG_RECORD_FACTORY(*args, **kwargs)
    record.request_id = get_request_id() or "-"
    record.task_id = get_task_id() or "-"
    return record


def _parse_log_level(log_level: str) -> int:
    value = getattr(logging, str(log_level or "INFO").upper(), None)
    return value if isinstance(value, int) else logging.INFO


def configure_logging(log_level: str) -> None:
    global _log_record_factory_configured

    if not _log_record_factory_configured:
        logging.setLogRecordFactory(_context_log_record_factory)
        _log_record_factory_configured = True

    starsorty_logger = logging.getLogger("starsorty")
    level = _parse_log_level(log_level)
    starsorty_logger.setLevel(level)
    starsorty_logger.propagate = False

    handler = next(
        (
            candidate
            for candidate in starsorty_logger.handlers
            if getattr(candidate, "_starsorty_context_handler", False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        handler._starsorty_context_handler = True  # type: ignore[attr-defined]
        starsorty_logger.addHandler(handler)

    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s task_id=%(task_id)s %(message)s"
        )
    )


def create_observed_task(
    coro: Awaitable[_T],
    *,
    task_id: str | None = None,
    request_id: str | None = None,
    name: str | None = None,
) -> asyncio.Task[_T]:
    effective_request_id = _normalize_context_id(request_id) or get_request_id()
    effective_task_id = _normalize_context_id(task_id) or get_task_id()

    async def _runner() -> _T:
        with bind_log_context(
            request_id=effective_request_id,
            task_id=effective_task_id,
        ):
            return await coro

    if name:
        task = asyncio.create_task(_runner(), name=name)
    else:
        task = asyncio.create_task(_runner())
    task._starsorty_request_id = effective_request_id  # type: ignore[attr-defined]
    task._starsorty_task_id = effective_task_id  # type: ignore[attr-defined]
    return task
