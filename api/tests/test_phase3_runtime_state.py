import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from api.app import db as db_mod
from api.app import runtime_store as runtime_store_mod
from api.app import state as state_mod
from api.app.db.runtime_guard import get_async_sqlite_runtime_issue
from api.app.db import schema as schema_db

ASYNC_SQLITE_RUNTIME_ISSUE = get_async_sqlite_runtime_issue()
pytestmark = pytest.mark.skipif(
    ASYNC_SQLITE_RUNTIME_ISSUE is not None,
    reason=ASYNC_SQLITE_RUNTIME_ISSUE or "",
)


def _run(coro):
    return asyncio.run(coro)


def _build_get_connection(db_path: Path):
    @asynccontextmanager
    async def _get_connection():
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    return _get_connection


def _reset_in_memory_state() -> None:
    state_mod.classification_state.clear()
    state_mod.classification_state.update(state_mod.CLASSIFICATION_STATE_DEFAULTS)
    state_mod.classification_control["stop_requested"] = False
    state_mod.classification_stop.clear()
    state_mod.quality_metrics.clear()
    state_mod.quality_metrics.update(state_mod.QUALITY_METRIC_DEFAULTS)


@pytest.fixture
def db_connection_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    get_connection = _build_get_connection(db_path)

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(runtime_store_mod, "get_connection", get_connection)

    _reset_in_memory_state()
    _run(schema_db.init_db())
    yield get_connection
    _reset_in_memory_state()


def test_quality_metrics_persist_to_sqlite_and_restore_after_local_reset(
    db_connection_factory,
) -> None:
    del db_connection_factory

    _run(
        state_mod._add_quality_metrics(
            api_request_total=4,
            api_error_total=1,
            api_request_latency_ms_total=120,
            cache_hit_total=6,
            cache_miss_total=2,
        )
    )

    state_mod.quality_metrics.clear()
    state_mod.quality_metrics.update(state_mod.QUALITY_METRIC_DEFAULTS)

    metrics = _run(state_mod._get_quality_metrics())

    assert metrics["api_request_total"] == 4
    assert metrics["api_error_total"] == 1
    assert metrics["api_request_latency_ms_avg"] == 30
    assert metrics["cache_hit_rate"] == 0.75


def test_classification_runtime_state_and_stop_request_persist_to_sqlite(
    db_connection_factory,
) -> None:
    del db_connection_factory

    _run(
        state_mod._update_classification_state(
            status="running",
            running=True,
            processed=7,
            failed=1,
            remaining=12,
            task_id="task-123",
        )
    )
    _run(state_mod._set_classification_stop_requested(True))

    _reset_in_memory_state()

    restored = _run(state_mod._get_classification_state())

    assert restored["status"] == "running"
    assert restored["running"] is True
    assert restored["processed"] == 7
    assert restored["failed"] == 1
    assert restored["remaining"] == 12
    assert restored["task_id"] == "task-123"
    assert _run(state_mod._is_classification_stop_requested()) is True


def test_initialize_runtime_state_clears_stale_running_snapshot_without_active_task(
    db_connection_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_connection_factory

    async def _fake_get_active_task(task_type: str):
        assert task_type == "classify"
        return None

    monkeypatch.setattr(db_mod, "get_active_task", _fake_get_active_task)

    _run(
        state_mod._update_classification_state(
            status="running",
            running=True,
            processed=3,
            task_id="stale-task",
        )
    )
    _run(state_mod._set_classification_stop_requested(True))

    _reset_in_memory_state()
    _run(state_mod.initialize_runtime_state())

    restored = _run(state_mod._get_classification_state())

    assert restored == state_mod.CLASSIFICATION_STATE_DEFAULTS
    assert _run(state_mod._is_classification_stop_requested()) is False
    assert state_mod.classification_stop.is_set() is False
