import asyncio
import io
import json
import os
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from api.app import export as export_mod
from api.app import rules as rules_mod
from api.app import taxonomy as taxonomy_mod
from api.app.db import helpers as helpers_db
from api.app.db import override as override_db
from api.app.db import repos as repos_db
from api.app.db.runtime_guard import get_async_sqlite_runtime_issue
from api.app.db import schema as schema_db
from api.app.db import search as search_db
from api.app.db import stats as stats_db

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


async def _insert_repos(get_connection, rows):
    async with get_connection() as conn:
        await conn.executemany(
            """
            INSERT INTO repos (
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users, readme_summary, ai_tags, ai_tag_ids, override_tags,
                override_tag_ids, summary_zh, override_summary_zh, ai_keywords, override_keywords
            ) VALUES (
                :full_name, :name, :owner, :html_url, :description, :language,
                :stargazers_count, :forks_count, :topics, :pushed_at, :updated_at, :starred_at,
                :star_users, :readme_summary, :ai_tags, :ai_tag_ids, :override_tags,
                :override_tag_ids, :summary_zh, :override_summary_zh, :ai_keywords, :override_keywords
            )
            """,
            rows,
        )
        await conn.commit()


def _repo_row(index: int, stars: int, token: str = "alpha") -> dict:
    return {
        "full_name": f"owner/repo-{index}",
        "name": f"{token}-repo-{index}",
        "owner": "owner",
        "html_url": f"https://example.com/owner/repo-{index}",
        "description": f"{token} description {index}",
        "language": "Python",
        "stargazers_count": stars,
        "forks_count": 0,
        "topics": json.dumps([token]),
        "pushed_at": "2026-03-01T00:00:00+00:00",
        "updated_at": "2026-03-01T00:00:00+00:00",
        "starred_at": "2026-03-01T00:00:00+00:00",
        "star_users": json.dumps([f"user-{index}"]),
        "readme_summary": f"{token} summary {index}",
        "ai_tags": json.dumps([]),
        "ai_tag_ids": json.dumps([]),
        "override_tags": json.dumps([]),
        "override_tag_ids": json.dumps([]),
        "summary_zh": None,
        "override_summary_zh": None,
        "ai_keywords": json.dumps([]),
        "override_keywords": json.dumps([]),
    }


def _sync_repo_payload(index: int, stars: int, users: list[str] | None = None) -> dict:
    return {
        "full_name": f"owner/repo-{index}",
        "name": f"repo-{index}",
        "owner": "owner",
        "html_url": f"https://example.com/owner/repo-{index}",
        "description": f"repo {index}",
        "language": "Python",
        "stargazers_count": stars,
        "forks_count": 0,
        "topics": ["alpha"],
        "pushed_at": "2026-03-01T00:00:00+00:00",
        "updated_at": "2026-03-01T00:00:00+00:00",
        "starred_at": "2026-03-01T00:00:00+00:00",
        "star_users": list(users or []),
    }


async def _collect_chunks(iterator):
    return [chunk async for chunk in iterator]


@pytest.fixture
def db_connection_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    get_connection = _build_get_connection(db_path)

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(override_db, "get_connection", get_connection)
    monkeypatch.setattr(search_db, "get_connection", get_connection)
    monkeypatch.setattr(repos_db, "get_connection", get_connection)
    monkeypatch.setattr(stats_db, "get_connection", get_connection)
    monkeypatch.setattr(search_db, "is_fts_enabled", lambda: False)

    _run(schema_db.init_db())
    return get_connection


def test_relevance_candidate_limit_keeps_true_total_and_exposes_page_cap(db_connection_factory, monkeypatch):
    monkeypatch.setattr(search_db, "RELEVANCE_CANDIDATE_LIMIT", 2)
    rows = [
        _repo_row(index=1, stars=100),
        _repo_row(index=2, stars=200),
        _repo_row(index=3, stars=300),
        _repo_row(index=4, stars=400),
    ]
    _run(_insert_repos(db_connection_factory, rows))

    page = _run(
        search_db.list_repos(q="alpha", sort="relevance", limit=10, offset=0)
    )

    assert page.total == 4
    assert page.has_more is False
    assert page.next_offset is None
    assert page.pagination_limited is True
    assert [item.full_name for item in page.items] == ["owner/repo-4", "owner/repo-3"]


def test_relevance_candidate_limit_exposes_next_offset_within_candidate_window(db_connection_factory, monkeypatch):
    monkeypatch.setattr(search_db, "RELEVANCE_CANDIDATE_LIMIT", 3)
    rows = [
        _repo_row(index=1, stars=100),
        _repo_row(index=2, stars=200),
        _repo_row(index=3, stars=300),
        _repo_row(index=4, stars=400),
    ]
    _run(_insert_repos(db_connection_factory, rows))

    page = _run(
        search_db.list_repos(q="alpha", sort="relevance", limit=1, offset=0)
    )

    assert page.total == 4
    assert page.has_more is True
    assert page.next_offset == 1
    assert page.pagination_limited is True
    assert [item.full_name for item in page.items] == ["owner/repo-4"]


def test_load_star_users_handles_large_input_by_chunking(
    db_connection_factory, monkeypatch
):
    monkeypatch.setattr(repos_db, "STAR_USER_LOOKUP_CHUNK_SIZE", 400)
    row_count = 1105
    rows = [_repo_row(index=i, stars=i) for i in range(row_count)]
    _run(_insert_repos(db_connection_factory, rows))

    lookup_input = [{"full_name": f"owner/repo-{i}"} for i in range(row_count)]
    users_map = _run(repos_db._load_star_users(lookup_input))

    assert len(users_map) == row_count
    assert users_map["owner/repo-0"] == ["user-0"]
    assert users_map[f"owner/repo-{row_count - 1}"] == [f"user-{row_count - 1}"]


def test_upsert_repos_commits_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeConnection:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []
            self.commit_count = 0

        async def executemany(self, query: str, params: list[dict]) -> None:
            assert "INSERT INTO repos" in query
            self.batch_sizes.append(len(params))

        async def commit(self) -> None:
            self.commit_count += 1

        async def rollback(self) -> None:
            raise AssertionError("rollback should not be used in successful batch path")

    @asynccontextmanager
    async def _fake_get_connection():
        yield fake_conn

    async def _fake_load_star_users(repos: list[dict]) -> dict:
        del repos
        return {}

    async def _fake_bump(conn) -> int:
        assert conn is fake_conn
        bump_calls.append("bump")
        return len(bump_calls)

    fake_conn = _FakeConnection()
    bump_calls: list[str] = []
    repos = [_sync_repo_payload(index=i, stars=i, users=[f"user-{i}"]) for i in range(5)]

    monkeypatch.setattr(repos_db, "REPO_UPSERT_BATCH_SIZE", 2)
    monkeypatch.setattr(repos_db, "get_connection", _fake_get_connection)
    monkeypatch.setattr(repos_db, "_load_star_users", _fake_load_star_users)
    monkeypatch.setattr(repos_db, "bump_repo_stats_version", _fake_bump)

    inserted = _run(repos_db.upsert_repos(repos))

    assert inserted == 5
    assert fake_conn.batch_sizes == [2, 2, 1]
    assert fake_conn.commit_count == 3
    assert len(bump_calls) == 3


def test_upsert_repos_keeps_star_user_merge_when_batched(
    db_connection_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run(_insert_repos(db_connection_factory, [_repo_row(index=1, stars=100)]))

    monkeypatch.setattr(repos_db, "REPO_UPSERT_BATCH_SIZE", 1)

    _run(
        repos_db.upsert_repos(
            [
                _sync_repo_payload(index=1, stars=120, users=["user-2"]),
                _sync_repo_payload(index=2, stars=80, users=["user-3"]),
            ]
        )
    )

    async def _fetch_star_users(full_name: str) -> list[str]:
        async with db_connection_factory() as conn:
            row = await (
                await conn.execute("SELECT star_users FROM repos WHERE full_name = ?", (full_name,))
            ).fetchone()
        return json.loads(row[0])

    assert _run(_fetch_star_users("owner/repo-1")) == ["user-1", "user-2"]
    assert _run(_fetch_star_users("owner/repo-2")) == ["user-3"]


def test_generate_obsidian_zip_streaming_yields_incremental_valid_zip() -> None:
    async def _repo_iter():
        yield {
            "full_name": "owner/repo-1",
            "name": "repo-1",
            "owner": "owner",
            "html_url": "https://example.com/owner/repo-1",
            "description": "repo 1",
            "language": "Python",
            "stargazers_count": 101,
            "forks_count": 3,
            "category": "AI",
            "tags": ["Agent"],
            "keywords": ["agent"],
            "starred_at": "2026-03-01T00:00:00+00:00",
            "summary_zh": "repo one",
        }
        yield {
            "full_name": "owner/repo-2",
            "name": "repo-2",
            "owner": "owner",
            "html_url": "https://example.com/owner/repo-2",
            "description": "repo 2",
            "language": "Go",
            "stargazers_count": 88,
            "forks_count": 1,
            "category": "Infra",
            "tags": ["Ops"],
            "keywords": ["infra"],
            "starred_at": "2026-03-02T00:00:00+00:00",
            "summary_zh": "repo two",
        }

    chunks = _run(_collect_chunks(export_mod.generate_obsidian_zip_streaming(_repo_iter())))

    assert len(chunks) >= 2
    archive = io.BytesIO(b"".join(chunks))
    with zipfile.ZipFile(archive, "r") as zf:
        names = sorted(zf.namelist())
        assert names == ["AI/owner_repo-1.md", "Infra/owner_repo-2.md"]
        first = zf.read("AI/owner_repo-1.md").decode("utf-8")
        second = zf.read("Infra/owner_repo-2.md").decode("utf-8")
    assert "# repo-1" in first
    assert "#Agent" in first
    assert "# repo-2" in second


def test_repo_lookup_tables_power_tag_and_user_filters(db_connection_factory) -> None:
    first = _repo_row(index=1, stars=100, token="agents")
    first["star_users"] = json.dumps(["alice", "bob"])
    first["ai_tags"] = json.dumps(["Agent"])
    first["ai_tag_ids"] = json.dumps(["agent"])
    first["override_tags"] = None
    first["override_tag_ids"] = None

    second = _repo_row(index=2, stars=200, token="rag")
    second["star_users"] = json.dumps(["carol"])
    second["ai_tags"] = json.dumps(["Ignored"])
    second["ai_tag_ids"] = json.dumps(["ignored"])
    second["override_tags"] = json.dumps(["RAG"])
    second["override_tag_ids"] = json.dumps(["rag"])

    _run(_insert_repos(db_connection_factory, [first, second]))

    tag_page = _run(search_db.list_repos(tag="rag"))
    user_page = _run(search_db.list_repos(star_user="alice"))
    stats_payload = _run(stats_db.get_repo_stats(refresh=True, use_snapshot=False))

    assert [item.full_name for item in tag_page.items] == ["owner/repo-2"]
    assert [item.full_name for item in user_page.items] == ["owner/repo-1"]
    assert any(item["name"] == "RAG" and item["count"] == 1 for item in stats_payload["tags"])
    assert any(item["name"] == "alice" and item["count"] == 1 for item in stats_payload["users"])


def test_manual_override_tag_updates_keep_lookup_history_and_training_consistent(
    db_connection_factory,
) -> None:
    row = _repo_row(index=3, stars=300, token="override")
    row["ai_tags"] = json.dumps(["Agent"])
    row["ai_tag_ids"] = json.dumps(["ai.agent"])
    row["override_tags"] = None
    row["override_tag_ids"] = None
    _run(_insert_repos(db_connection_factory, [row]))

    _run(
        override_db.update_override(
            "owner/repo-3",
            {
                "tags": ["LLM", "后台服务"],
                "tag_ids": ["ai.llm", "dev.backend"],
                "note": "manual review",
            },
        )
    )

    async def _fetch_effective_tags() -> list[tuple[str, str]]:
        async with db_connection_factory() as conn:
            rows = await (
                await conn.execute(
                    """
                    SELECT ret.tag, ret.tag_id
                    FROM repo_effective_tags ret
                    JOIN repos ON repos.id = ret.repo_id
                    WHERE repos.full_name = ?
                    ORDER BY ret.tag_id ASC, ret.tag ASC
                    """,
                    ("owner/repo-3",),
                )
            ).fetchall()
        return [(row["tag"], row["tag_id"]) for row in rows]

    async def _fetch_history_and_training() -> tuple[list[str], list[str]]:
        async with db_connection_factory() as conn:
            history = await (
                await conn.execute(
                    "SELECT tags FROM override_history WHERE full_name = ? ORDER BY id DESC LIMIT 1",
                    ("owner/repo-3",),
                )
            ).fetchone()
            sample = await (
                await conn.execute(
                    "SELECT after_tag_ids FROM training_samples WHERE full_name = ? ORDER BY id DESC LIMIT 1",
                    ("owner/repo-3",),
                )
            ).fetchone()
        return json.loads(history["tags"]), json.loads(sample["after_tag_ids"])

    assert _run(_fetch_effective_tags()) == [
        ("LLM", "ai.llm"),
        ("后台服务", "dev.backend"),
    ]
    assert [item.full_name for item in _run(search_db.list_repos(tag="ai.llm")).items] == ["owner/repo-3"]
    assert [item.full_name for item in _run(search_db.list_repos(tag="后台服务")).items] == ["owner/repo-3"]
    assert _run(_fetch_history_and_training()) == (
        ["LLM", "后台服务"],
        ["ai.llm", "dev.backend"],
    )

    _run(override_db.update_override("owner/repo-3", {"tags": None, "tag_ids": None}))

    assert _run(_fetch_effective_tags()) == [("Agent", "ai.agent")]


def test_taxonomy_cache_reloads_on_file_change(tmp_path, monkeypatch):
    monkeypatch.setattr(taxonomy_mod, "TAXONOMY_CACHE_TTL_SECONDS", 300)
    taxonomy_mod._taxonomy_cache.clear()

    taxonomy_path = tmp_path / "taxonomy.yaml"
    taxonomy_path.write_text(
        "categories:\n"
        "  - name: CatA\n"
        "    subcategories: [SubA]\n"
        "tags: []\n",
        encoding="utf-8",
    )

    first = taxonomy_mod.load_taxonomy(str(taxonomy_path))
    second = taxonomy_mod.load_taxonomy(str(taxonomy_path))
    assert first is second
    assert first["categories"][0]["name"] == "CatA"

    time.sleep(0.01)
    taxonomy_path.write_text(
        "categories:\n"
        "  - name: CatB\n"
        "    subcategories: [SubB]\n"
        "tags: []\n",
        encoding="utf-8",
    )
    os.utime(taxonomy_path, None)

    reloaded = taxonomy_mod.load_taxonomy(str(taxonomy_path))
    assert reloaded["categories"][0]["name"] == "CatB"
    assert reloaded is not second


def test_rules_cache_reloads_on_file_change(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_mod, "RULES_CACHE_TTL_SECONDS", 300)
    rules_mod._rules_raw_cache.clear()
    rules_mod._rules_file_cache.clear()

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "r1",
                        "must_keywords": ["alpha"],
                        "candidate_category": "dev",
                        "candidate_subcategory": "tools",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = rules_mod.load_rules("", fallback_path=rules_path)
    second = rules_mod.load_rules("", fallback_path=rules_path)
    assert first[0]["rule_id"] == "r1"
    assert second[0]["rule_id"] == "r1"

    time.sleep(0.01)
    rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "r2",
                        "must_keywords": ["beta"],
                        "candidate_category": "ops",
                        "candidate_subcategory": "infra",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.utime(rules_path, None)

    reloaded = rules_mod.load_rules("", fallback_path=rules_path)
    assert reloaded[0]["rule_id"] == "r2"


def test_init_db_reuses_existing_fts_objects_without_dropping_rows(db_connection_factory):
    if not schema_db.is_fts_enabled():
        pytest.skip("SQLite FTS5 unavailable in current test environment")

    rows = [_repo_row(index=1, stars=100)]
    _run(_insert_repos(db_connection_factory, rows))

    async def _count_fts_rows() -> int:
        async with db_connection_factory() as conn:
            row = await (await conn.execute("SELECT COUNT(*) FROM repos_fts")).fetchone()
        return int(row[0] or 0)

    first_count = _run(_count_fts_rows())
    assert first_count == 1

    _run(schema_db.init_db())

    second_count = _run(_count_fts_rows())
    assert second_count == 1


def test_retry_on_lock_records_conflicts_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    recorded: list[dict[str, int]] = []
    sleeps: list[float] = []

    async def _fake_record(**delta: int) -> None:
        recorded.append(delta)

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def _flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise helpers_db.sqlite3.OperationalError("database is locked")
        return "ok"

    monkeypatch.setattr(helpers_db, "_record_lock_metrics", _fake_record)
    monkeypatch.setattr(helpers_db.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(helpers_db.random, "uniform", lambda _min, _max: 0.0)

    wrapped = helpers_db._retry_on_lock(max_attempts=5, base_delay=0.05, max_delay=0.5)(_flaky)

    result = _run(wrapped())

    assert result == "ok"
    assert recorded == [
        {"db_lock_conflict_total": 1, "db_lock_retry_total": 1},
        {"db_lock_conflict_total": 1, "db_lock_retry_total": 1},
    ]
    assert sleeps == [0.05, 0.1]


def test_retry_on_lock_records_exhausted_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[dict[str, int]] = []
    sleeps: list[float] = []

    async def _fake_record(**delta: int) -> None:
        recorded.append(delta)

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def _always_locked() -> None:
        raise helpers_db.sqlite3.OperationalError("database table is locked")

    monkeypatch.setattr(helpers_db, "_record_lock_metrics", _fake_record)
    monkeypatch.setattr(helpers_db.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(helpers_db.random, "uniform", lambda _min, _max: 0.0)

    wrapped = helpers_db._retry_on_lock(max_attempts=3, base_delay=0.05, max_delay=0.5)(_always_locked)

    with pytest.raises(helpers_db.sqlite3.OperationalError, match="locked"):
        _run(wrapped())

    assert recorded == [
        {"db_lock_conflict_total": 1, "db_lock_retry_total": 1},
        {"db_lock_conflict_total": 1, "db_lock_retry_total": 1},
        {"db_lock_conflict_total": 1, "db_lock_retry_exhausted_total": 1},
    ]
    assert sleeps == [0.05, 0.1]
