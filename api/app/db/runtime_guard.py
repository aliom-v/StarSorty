import sys
from typing import Sequence

MIN_SUPPORTED_PYTHON_MINOR = 11
MAX_SUPPORTED_PYTHON_MINOR = 13
SUPPORTED_PYTHON_RANGE = f"3.{MIN_SUPPORTED_PYTHON_MINOR}-3.{MAX_SUPPORTED_PYTHON_MINOR}"
DOCKER_FALLBACK_PYTHON = "3.11"


class AsyncSqliteRuntimeUnsupportedError(RuntimeError):
    """Raised when the local Python runtime is unsupported for async SQLite."""


def _version_tuple(version_info: object | None = None) -> tuple[int, int]:
    current = version_info or sys.version_info
    if hasattr(current, "major") and hasattr(current, "minor"):
        return int(current.major), int(current.minor)
    if isinstance(current, Sequence) and len(current) >= 2:
        return int(current[0]), int(current[1])
    raise TypeError("version_info must expose major/minor or be an indexable sequence")


def get_async_sqlite_runtime_issue(version_info: object | None = None) -> str | None:
    major, minor = _version_tuple(version_info)
    if major == 3 and MIN_SUPPORTED_PYTHON_MINOR <= minor <= MAX_SUPPORTED_PYTHON_MINOR:
        return None
    if major == 3 and minor >= 14:
        return (
            f"Python {major}.{minor} is currently unsupported for StarSorty async SQLite runtime. "
            "aiosqlite can hang while opening SQLite connections in this environment; "
            f"use Python {SUPPORTED_PYTHON_RANGE} or Docker Python {DOCKER_FALLBACK_PYTHON} instead."
        )
    return (
        f"Python {major}.{minor} is unsupported for StarSorty async SQLite runtime; "
        f"use Python {SUPPORTED_PYTHON_RANGE} or Docker Python {DOCKER_FALLBACK_PYTHON} instead."
    )


def ensure_async_sqlite_runtime_supported(version_info: object | None = None) -> None:
    issue = get_async_sqlite_runtime_issue(version_info)
    if issue:
        raise AsyncSqliteRuntimeUnsupportedError(issue)
