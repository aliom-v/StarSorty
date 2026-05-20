import asyncio
import json

from api.app.db import user as user_db


class _FakeCursor:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


class _FakeResult:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, repo_row: dict | None, preference_row: dict | None) -> None:
        self.repo_row = repo_row
        self.preference_row = preference_row
        self.insert_params = None
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def execute(self, sql: str, params=()):
        normalized_sql = " ".join(sql.split())
        if "FROM repos" in normalized_sql:
            return _FakeResult(self.repo_row)
        if "FROM user_preferences" in normalized_sql:
            return _FakeResult(self.preference_row)
        if normalized_sql.startswith("INSERT INTO user_preferences"):
            self.insert_params = params
            return _FakeCursor(rowcount=1)
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.committed = True


def _run(coro):
    return asyncio.run(coro)


def test_record_manual_override_preference_rejects_many_to_one_tag_learning(
    monkeypatch,
):
    fake_connection = _FakeConnection(
        repo_row={
            "category": "dev",
            "subcategory": "frontend",
            "ai_tag_ids": json.dumps(["ai.llm", "dev.backend"]),
            "override_category": "ai",
            "override_subcategory": "llm",
            "override_tag_ids": json.dumps(["productivity.notes"]),
        },
        preference_row={
            "tag_mapping_json": "{}",
            "rule_priority_json": "{}",
            "updated_at": "2026-05-20T00:00:00+00:00",
        },
    )

    monkeypatch.setattr(user_db, "get_connection", lambda: fake_connection)

    result = _run(user_db.record_manual_override_preference("owner/repo"))

    assert result["tag_mapping"] == {
        "classification:dev/frontend": "classification:ai/llm",
    }
    assert fake_connection.committed is True
    assert json.loads(fake_connection.insert_params[1]) == {
        "classification:dev/frontend": "classification:ai/llm",
    }


def test_record_manual_override_preference_keeps_one_to_one_tag_learning(
    monkeypatch,
):
    fake_connection = _FakeConnection(
        repo_row={
            "category": "dev",
            "subcategory": "frontend",
            "ai_tag_ids": json.dumps(["ai.llm"]),
            "override_category": "dev",
            "override_subcategory": "frontend",
            "override_tag_ids": json.dumps(["ai.agent"]),
        },
        preference_row={
            "tag_mapping_json": "{}",
            "rule_priority_json": "{}",
            "updated_at": "2026-05-20T00:00:00+00:00",
        },
    )

    monkeypatch.setattr(user_db, "get_connection", lambda: fake_connection)

    result = _run(user_db.record_manual_override_preference("owner/repo"))

    assert result["tag_mapping"] == {"ai.llm": "ai.agent"}
    assert json.loads(fake_connection.insert_params[1]) == {"ai.llm": "ai.agent"}
