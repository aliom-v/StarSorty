import asyncio
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
