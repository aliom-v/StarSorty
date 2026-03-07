import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from api.app.db import classification as classification_db
from api.app.db import repos as repos_db
from api.app.db import schema as schema_db
from api.app.db import stats as stats_db


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


def _repo_row(index: int, category: str | None = None, users: list[str] | None = None) -> dict:
    return {
        "full_name": f"owner/repo-{index}",
        "name": f"repo-{index}",
        "owner": "owner",
        "html_url": f"https://example.com/owner/repo-{index}",
        "description": f"description {index}",
        "language": "Python",
        "stargazers_count": index,
        "forks_count": 0,
        "topics": json.dumps(["python"]),
        "pushed_at": "2026-03-01T00:00:00+00:00",
        "updated_at": "2026-03-01T00:00:00+00:00",
        "starred_at": "2026-03-01T00:00:00+00:00",
        "star_users": users or [f"user-{index}"],
        "category": category,
    }


async def _insert_repos(get_connection, rows):
    async with get_connection() as conn:
        await conn.executemany(
            """
            INSERT INTO repos (
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users, category
            ) VALUES (
                :full_name, :name, :owner, :html_url, :description, :language,
                :stargazers_count, :forks_count, :topics, :pushed_at, :updated_at, :starred_at,
                :star_users, :category
            )
            """,
            [
                {
                    **row,
                    "star_users": json.dumps(row.get("star_users") or []),
                }
                for row in rows
            ],
        )
        await conn.commit()


@pytest.fixture
def db_connection_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    get_connection = _build_get_connection(db_path)

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(stats_db, "get_connection", get_connection)
    monkeypatch.setattr(repos_db, "get_connection", get_connection)
    monkeypatch.setattr(classification_db, "get_connection", get_connection)

    _run(schema_db.init_db())
    return get_connection


def test_repo_stats_snapshot_reuses_same_version_and_refreshes_after_repo_write(
    db_connection_factory, monkeypatch
):
    _run(_insert_repos(db_connection_factory, [_repo_row(1), _repo_row(2)]))

    calls = {"count": 0}
    original_compute = stats_db._compute_repo_stats

    async def _counted_compute(conn):
        calls["count"] += 1
        return await original_compute(conn)

    monkeypatch.setattr(stats_db, "_compute_repo_stats", _counted_compute)

    first = _run(stats_db.get_repo_stats())
    second = _run(stats_db.get_repo_stats())

    assert first["total"] == 2
    assert second["total"] == 2
    assert calls["count"] == 1

    _run(repos_db.upsert_repos([_repo_row(3)]))
    third = _run(stats_db.get_repo_stats())

    assert third["total"] == 3
    assert calls["count"] == 2


def test_repo_stats_snapshot_refreshes_after_classification_update(db_connection_factory):
    _run(_insert_repos(db_connection_factory, [_repo_row(1), _repo_row(2)]))

    initial = _run(stats_db.get_repo_stats())
    assert initial["categories"][0]["name"] == "uncategorized"
    assert initial["categories"][0]["count"] == 2

    _run(
        classification_db.update_classification(
            full_name="owner/repo-1",
            category="ai",
            subcategory="llm",
            confidence=0.9,
            tags=["LLM"],
            tag_ids=["ai.llm"],
            provider="test",
            model="test-model",
        )
    )

    refreshed = _run(stats_db.get_repo_stats())
    category_counts = {item["name"]: item["count"] for item in refreshed["categories"]}

    assert category_counts["ai"] == 1
    assert category_counts["uncategorized"] == 1
    assert refreshed["unclassified"] == 1
