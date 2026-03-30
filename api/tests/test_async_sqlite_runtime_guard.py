import pytest

from api.app.db.runtime_guard import (
    AsyncSqliteRuntimeUnsupportedError,
    ensure_async_sqlite_runtime_supported,
    get_async_sqlite_runtime_issue,
)


def test_supported_python_range_has_no_runtime_issue() -> None:
    assert get_async_sqlite_runtime_issue((3, 11, 0)) is None
    assert get_async_sqlite_runtime_issue((3, 13, 9)) is None


def test_python_314_reports_async_sqlite_runtime_issue() -> None:
    issue = get_async_sqlite_runtime_issue((3, 14, 0))

    assert issue is not None
    assert "Python 3.14" in issue
    assert "aiosqlite can hang" in issue
    assert "3.11-3.13" in issue


def test_unsupported_runtime_guard_raises_clear_error() -> None:
    with pytest.raises(AsyncSqliteRuntimeUnsupportedError, match="Docker Python 3.11"):
        ensure_async_sqlite_runtime_supported((3, 10, 14))
