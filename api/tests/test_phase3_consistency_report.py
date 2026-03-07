import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from api.app.db import consistency as consistency_db
from api.app.db import schema as schema_db
from api.app.routes import stats as stats_routes


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
    taxonomy_path = tmp_path / "taxonomy.yaml"
    taxonomy_path.write_text(
        "version: 1\n"
        "categories:\n"
        "  - name: ai\n"
        "    subcategories: [llm]\n"
        "  - name: uncategorized\n"
        "    subcategories: [other]\n"
        "tags:\n"
        "  - 工具\n"
        "  - LLM\n",
        encoding="utf-8",
    )
    get_connection = _build_get_connection(db_path)

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(consistency_db, "get_connection", get_connection)

    _run(schema_db.init_db())
    return get_connection, taxonomy_path


async def _insert_repo(get_connection, **values):
    defaults = {
        "full_name": "owner/repo-1",
        "name": "repo-1",
        "owner": "owner",
        "html_url": "https://example.com/owner/repo-1",
        "description": "desc",
        "language": "Python",
        "stargazers_count": 1,
        "forks_count": 0,
        "topics": json.dumps(["python"]),
        "pushed_at": "2026-03-01T00:00:00+00:00",
        "updated_at": "2026-03-01T00:00:00+00:00",
        "starred_at": "2026-03-01T00:00:00+00:00",
        "star_users": json.dumps(["alice"]),
        "category": None,
        "subcategory": None,
        "override_category": None,
        "override_subcategory": None,
        "ai_tags": json.dumps([]),
        "ai_tag_ids": json.dumps([]),
        "override_tags": None,
        "override_tag_ids": None,
    }
    defaults.update(values)
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO repos (
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users, category, subcategory, override_category, override_subcategory,
                ai_tags, ai_tag_ids, override_tags, override_tag_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(defaults[key] for key in (
                "full_name", "name", "owner", "html_url", "description", "language",
                "stargazers_count", "forks_count", "topics", "pushed_at", "updated_at", "starred_at",
                "star_users", "category", "subcategory", "override_category", "override_subcategory",
                "ai_tags", "ai_tag_ids", "override_tags", "override_tag_ids"
            )),
        )
        await conn.commit()


def test_consistency_report_detects_fts_drift_and_invalid_values(db_connection_factory, monkeypatch):
    get_connection, taxonomy_path = db_connection_factory
    _run(
        _insert_repo(
            get_connection,
            category="invalid-category",
            subcategory="bad-subcategory",
            ai_tags=json.dumps(["工具"]),
            ai_tag_ids=json.dumps(["unknown-tag-id"]),
        )
    )

    async def _damage_fts():
        async with get_connection() as conn:
            await conn.execute("DELETE FROM repos_fts")
            await conn.commit()

    _run(_damage_fts())
    monkeypatch.setattr(consistency_db, "is_fts_enabled", lambda: True)

    report = _run(consistency_db.get_repo_consistency_report(str(taxonomy_path)))
    issue_codes = {item["code"] for item in report["issues"]}

    assert report["ok"] is False
    assert report["fts"]["drift"] == 1
    assert "fts_row_count_mismatch" in issue_codes
    assert "invalid_categories" in issue_codes
    assert "non_normalized_ai_tag_ids" in issue_codes


def test_consistency_report_detects_malformed_json_and_orphan_subcategory(db_connection_factory, monkeypatch):
    get_connection, taxonomy_path = db_connection_factory
    _run(
        _insert_repo(
            get_connection,
            override_category=None,
            override_subcategory="llm",
            override_tags="{bad json}",
            override_tag_ids="{bad json}",
        )
    )
    monkeypatch.setattr(consistency_db, "is_fts_enabled", lambda: False)

    report = _run(consistency_db.get_repo_consistency_report(str(taxonomy_path)))
    issue_codes = {item["code"] for item in report["issues"]}

    assert "orphan_subcategories" in issue_codes
    assert "malformed_override_tags" in issue_codes
    assert "malformed_override_tag_ids" in issue_codes


def test_consistency_route_has_admin_dependency() -> None:
    route = next(
        route
        for route in stats_routes.router.routes
        if getattr(route, "path", None) == "/metrics/consistency"
    )
    dependency_calls = [dependency.dependency for dependency in route.dependencies]
    assert stats_routes.require_admin in dependency_calls
