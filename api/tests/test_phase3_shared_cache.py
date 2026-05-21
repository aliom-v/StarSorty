import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from api.app import cache as cache_mod
from api.app import cache_store as cache_store_mod
from api.app.db.runtime_guard import get_async_sqlite_runtime_issue
from api.app import deps as deps_mod
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


@pytest.fixture
def db_connection_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    get_connection = _build_get_connection(db_path)

    async def _noop_record_cache_metric(hit: bool) -> None:
        del hit

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(cache_store_mod, "get_connection", get_connection)
    monkeypatch.setattr(cache_mod, "_record_cache_metric", _noop_record_cache_metric)

    _run(schema_db.init_db())
    return get_connection


def test_shared_repos_namespace_invalidates_query_cache_across_instances(
    db_connection_factory,
) -> None:
    del db_connection_factory

    cache_a = cache_mod.SimpleCache()
    cache_b = cache_mod.SimpleCache()
    repo_cache_key = deps_mod._repos_cache_key(
        q="agents",
        language="python",
        min_stars=10,
        category="ai",
        subcategory="agent",
        tag=None,
        tags="agent,rag",
        tag_mode="or",
        sort="stars",
        user_id="global",
        star_user=None,
        limit=20,
        offset=0,
    )

    payload = {
        "total": 1,
        "items": [{"full_name": "owner/repo"}],
        "has_more": False,
        "next_offset": None,
        "pagination_limited": False,
    }
    _run(cache_a.set(repo_cache_key, payload, ttl=60))

    assert _run(cache_a.get(repo_cache_key)) == payload
    assert _run(cache_b.get(repo_cache_key)) == payload

    _run(cache_b.invalidate_prefix("repos"))

    assert _run(cache_a.get(repo_cache_key)) is None
    assert _run(cache_b.get(repo_cache_key)) is None


def test_shared_repos_namespace_loads_cached_value_across_instances(
    db_connection_factory,
) -> None:
    del db_connection_factory

    cache_a = cache_mod.SimpleCache()
    cache_b = cache_mod.SimpleCache()
    repo_cache_key = deps_mod._repos_cache_key(
        q="graph",
        language="rust",
        min_stars=50,
        category="infra",
        subcategory="graph",
        tag=None,
        tags="graph,db",
        tag_mode="and",
        sort="updated",
        user_id="global",
        star_user=None,
        limit=10,
        offset=5,
    )
    payload = {
        "total": 2,
        "items": [{"full_name": "owner/repo-1"}, {"full_name": "owner/repo-2"}],
        "has_more": True,
        "next_offset": 15,
        "pagination_limited": False,
    }

    _run(cache_a.set(repo_cache_key, payload, ttl=60))

    assert _run(cache_b.get(repo_cache_key)) == payload


def test_repo_namespace_invalidation_does_not_evict_unrelated_local_keys(
    db_connection_factory,
) -> None:
    del db_connection_factory

    cache_a = cache_mod.SimpleCache()
    cache_b = cache_mod.SimpleCache()

    _run(cache_a.set("misc:demo", {"total": 3}, ttl=60))
    _run(cache_a.set("repos:demo", {"items": []}, ttl=60))

    _run(cache_b.invalidate_prefix("repos"))

    assert _run(cache_a.get("misc:demo")) == {"total": 3}
    assert _run(cache_a.get("repos:demo")) is None


def test_expired_shared_cache_entries_can_be_cleaned_in_batches(
    db_connection_factory,
) -> None:
    del db_connection_factory

    now = time.time()
    _run(
        cache_store_mod.store_shared_cache_entry(
            "repos:expired:one",
            namespace="repos",
            namespace_version=1,
            payload={"items": [{"full_name": "old/one"}]},
            expires_at=now - 10,
            enforce_limits=False,
        )
    )
    _run(
        cache_store_mod.store_shared_cache_entry(
            "repos:expired:two",
            namespace="repos",
            namespace_version=1,
            payload={"items": [{"full_name": "old/two"}]},
            expires_at=now - 5,
            enforce_limits=False,
        )
    )
    _run(
        cache_store_mod.store_shared_cache_entry(
            "repos:fresh",
            namespace="repos",
            namespace_version=1,
            payload={"items": [{"full_name": "new/repo"}]},
            expires_at=now + 60,
            enforce_limits=False,
        )
    )

    metrics = _run(cache_store_mod.get_shared_cache_metrics(now=now))
    assert metrics["entry_count"] == 3
    assert metrics["expired_count"] == 2
    assert metrics["approx_payload_bytes"] > 0

    deleted = _run(
        cache_store_mod.cleanup_expired_shared_cache_entries(
            namespace="repos",
            now=now,
            limit=1,
        )
    )

    assert deleted == 1
    metrics = _run(cache_store_mod.get_shared_cache_metrics(now=now))
    assert metrics["entry_count"] == 2
    assert metrics["expired_count"] == 1

    deleted = _run(
        cache_store_mod.cleanup_expired_shared_cache_entries(
            namespace="repos",
            now=now,
            limit=10,
        )
    )

    assert deleted == 1
    assert _run(cache_store_mod.load_shared_cache_entry("repos:fresh")) is not None


def test_shared_cache_limits_prune_oldest_entries_and_bytes(
    db_connection_factory,
) -> None:
    del db_connection_factory

    now = time.time()
    for key in ("repos:one", "repos:two", "repos:three"):
        _run(
            cache_store_mod.store_shared_cache_entry(
                key,
                namespace="repos",
                namespace_version=1,
                payload={"blob": key * 10},
                expires_at=now + 60,
                enforce_limits=False,
            )
        )

    deleted = _run(
        cache_store_mod.enforce_shared_cache_limits(
            "repos",
            max_entries=2,
            max_bytes=10_000,
            now=now,
        )
    )

    assert deleted == 1
    assert _run(cache_store_mod.load_shared_cache_entry("repos:one")) is None
    assert _run(cache_store_mod.load_shared_cache_entry("repos:two")) is not None
    assert _run(cache_store_mod.load_shared_cache_entry("repos:three")) is not None

    deleted = _run(
        cache_store_mod.enforce_shared_cache_limits(
            "repos",
            max_entries=10,
            max_bytes=80,
            now=now,
        )
    )

    assert deleted >= 1
    metrics = _run(cache_store_mod.get_shared_cache_metrics(namespace="repos", now=now))
    assert metrics["entry_count"] <= 1
    assert metrics["approx_payload_bytes"] <= 80 or metrics["entry_count"] == 0


def test_cache_records_local_shared_and_miss_sources(
    db_connection_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_connection_factory

    sources: list[str] = []

    async def _capture_cache_metric(source: str) -> None:
        sources.append(source)

    monkeypatch.setattr(cache_mod, "_record_cache_metric", _capture_cache_metric)

    cache_a = cache_mod.SimpleCache()
    cache_b = cache_mod.SimpleCache()
    payload = {"total": 1, "items": [{"full_name": "owner/repo"}]}

    _run(cache_a.set("repos:source", payload, ttl=60))

    assert _run(cache_a.get("repos:source")) == payload
    assert _run(cache_b.get("repos:source")) == payload
    assert _run(cache_b.get("repos:missing")) is None

    assert sources == ["local", "shared", "miss"]
