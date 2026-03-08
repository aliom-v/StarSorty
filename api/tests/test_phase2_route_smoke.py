import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from api.app.classification.engine import (
    ClassificationOutcome,
    PendingAIClassification,
    PreparedClassification,
)
from api.app.deps import require_admin
from api.app.observability import (
    bind_log_context,
    create_observed_task,
    get_request_id,
    get_task_id,
    resolve_request_id,
)
from api.app.routes import classify as classify_routes
from api.app.routes import repos as repos_routes
from api.app.routes import settings as settings_routes
from api.app.routes import stats as stats_routes
from api.app.routes import sync as sync_routes
from api.app.routes import tasks as tasks_routes
from api.app.routes import user as user_routes
from api.app.schemas import (
    BackgroundClassifyRequest,
    ClassifyRequest,
    ClickFeedbackRequest,
    OverrideRequest,
    SearchFeedbackRequest,
    SettingsRequest,
    UserPreferencesRequest,
)


def _run(coro):
    return asyncio.run(coro)


def _dependency_calls(router, path: str) -> list:
    route = next(route for route in router.routes if getattr(route, "path", None) == path)
    return [dependency.dependency for dependency in route.dependencies]


def _repo_payload(full_name: str = "owner/repo") -> dict:
    return {
        "full_name": full_name,
        "name": full_name.split("/")[-1],
        "owner": full_name.split("/")[0],
        "html_url": f"https://github.com/{full_name}",
        "description": "Repository description",
        "language": "Python",
        "stargazers_count": 42,
        "forks_count": 7,
        "topics": ["ai"],
        "star_users": ["demo"],
        "category": "ai",
        "subcategory": "agents",
        "tags": ["Agent"],
        "tag_ids": ["ai.agent"],
        "ai_category": None,
        "ai_subcategory": None,
        "ai_confidence": None,
        "ai_tags": [],
        "ai_tag_ids": [],
        "ai_keywords": [],
        "ai_provider": None,
        "ai_model": None,
        "ai_reason": None,
        "ai_decision_source": None,
        "ai_rule_candidates": [],
        "ai_updated_at": None,
        "override_category": None,
        "override_subcategory": None,
        "override_tags": [],
        "override_tag_ids": [],
        "override_note": None,
        "override_summary_zh": None,
        "override_keywords": [],
        "readme_summary": None,
        "readme_fetched_at": None,
        "pushed_at": "2026-03-01T00:00:00+00:00",
        "updated_at": "2026-03-01T00:00:00+00:00",
        "starred_at": "2026-03-01T00:00:00+00:00",
        "summary_zh": None,
        "keywords": [],
        "search_score": None,
        "match_reasons": [],
    }


@pytest.fixture
def admin_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret")


@pytest.fixture
def disable_limiters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_routes.limiter, "enabled", False)
    monkeypatch.setattr(classify_routes.limiter, "enabled", False)
    monkeypatch.setattr(repos_routes.limiter, "enabled", False)
    monkeypatch.setattr(user_routes.limiter, "enabled", False)


def test_sync_status_and_sync_queue(disable_limiters: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_status() -> dict:
        return {
            "last_sync_at": "2026-03-07T00:00:00+00:00",
            "last_result": "ok",
            "last_message": "done",
        }

    registered: list[tuple] = []
    task_created = {"done_callback_added": False}

    async def _fake_register_task(task_id: str, task_type: str, **kwargs) -> None:
        registered.append((task_id, task_type, kwargs))

    class _FakeTask:
        def add_done_callback(self, callback) -> None:
            del callback
            task_created["done_callback_added"] = True

    def _fake_create_observed_task(coro, *, task_id=None, request_id=None, name=None):
        del task_id, request_id, name
        coro.close()
        return _FakeTask()

    monkeypatch.setattr(sync_routes, "get_sync_status", _fake_status)
    monkeypatch.setattr(sync_routes, "_register_task", _fake_register_task)
    monkeypatch.setattr(sync_routes, "create_observed_task", _fake_create_observed_task)
    monkeypatch.setattr(sync_routes.uuid, "uuid4", lambda: "sync-task-id")

    status_response = _run(sync_routes.status())
    assert status_response.last_result == "ok"

    dependency_calls = _dependency_calls(sync_routes.router, "/sync")
    assert require_admin in dependency_calls

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    queue_response = _run(sync_routes.sync(request))
    assert queue_response.task_id == "sync-task-id"
    assert queue_response.status == "queued"
    assert registered == [("sync-task-id", "sync", {"payload": {}})]
    assert task_created["done_callback_added"] is True


def test_classify_force_queue_and_background_controls(
    admin_token_env: None,
    disable_limiters: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple] = []
    started_payloads: list[tuple] = []

    async def _fake_register_task(task_id: str, task_type: str, message: str | None = None, payload: dict | None = None) -> None:
        registered.append((task_id, task_type, message, payload))

    async def _fake_start(payload, task_id: str, allow_fallback: bool) -> bool:
        started_payloads.append((payload, task_id, allow_fallback))
        return True

    async def _fake_state() -> dict:
        return {
            "running": False,
            "started_at": None,
            "finished_at": None,
            "processed": 0,
            "failed": 0,
            "remaining": 0,
            "last_error": None,
            "batch_size": 10,
            "concurrency": 2,
            "task_id": "stale-task-id",
        }

    updated_state: list[dict] = []

    async def _fake_update_state(**updates: object) -> None:
        updated_state.append(updates)

    monkeypatch.setattr(
        classify_routes,
        "get_settings",
        lambda: SimpleNamespace(ai_taxonomy_path="taxonomy.json", rules_json="[]"),
    )
    monkeypatch.setattr(classify_routes, "load_taxonomy", lambda path: {"path": path})
    monkeypatch.setattr(classify_routes, "_register_task", _fake_register_task)
    monkeypatch.setattr(classify_routes, "_start_background_classify", _fake_start)
    monkeypatch.setattr(classify_routes, "_get_classification_state", _fake_state)
    monkeypatch.setattr(classify_routes, "_update_classification_state", _fake_update_state)
    monkeypatch.setattr(classify_routes.uuid, "uuid4", lambda: "classify-task-id")

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    payload = ClassifyRequest(limit=9999, force=True, include_readme=False, preference_user="demo")
    response = _run(classify_routes.classify(request, payload))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 202
    assert json.loads(response.body) == {
        "task_id": "classify-task-id",
        "status": "queued",
        "message": "Classification queued",
    }
    assert registered[0][0] == "classify-task-id"
    force_payload = started_payloads[0][0]
    assert force_payload.force is True
    assert force_payload.concurrency == classify_routes.DEFAULT_CLASSIFY_CONCURRENCY
    assert force_payload.limit == classify_routes.CLASSIFY_BATCH_SIZE_MAX

    background_response = _run(
        classify_routes.classify_background(
            request,
            BackgroundClassifyRequest(limit=10, force=False, include_readme=True, concurrency=2),
        )
    )
    assert background_response.started is True
    assert background_response.running is True

    status_response = _run(classify_routes.classify_status())
    assert status_response.running is False
    assert status_response.task_id is None

    classify_routes.classification_stop.clear()
    try:
        stop_response = _run(classify_routes.classify_stop())
        assert stop_response == {"stopped": True}
        assert classify_routes.classification_stop.is_set() is True
        assert updated_state[-1] == {"last_error": "Stopped by user"}
    finally:
        classify_routes.classification_stop.clear()


def test_classify_foreground_returns_summary_and_invalidates_cache(
    disable_limiters: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repos_to_classify = [{"full_name": "owner/repo-1"}, {"full_name": "owner/repo-2"}]
    captured = {"invalidate": [], "select": None, "classify": None}

    async def _fake_select(limit: int, force: bool):
        captured["select"] = (limit, force)
        return repos_to_classify

    async def _fake_preferences(user_id: str) -> dict:
        return {"user_id": user_id, "tag_mapping": {}, "rule_priority": {}}

    async def _fake_classify(*args, **kwargs):
        captured["classify"] = {"args": args, "kwargs": kwargs}
        return 1, 1

    async def _fake_remaining() -> int:
        return 5

    async def _fake_invalidate(prefix: str) -> None:
        captured["invalidate"].append(prefix)

    monkeypatch.setattr(
        classify_routes,
        "get_settings",
        lambda: SimpleNamespace(ai_taxonomy_path="taxonomy.json", rules_json="[]"),
    )
    monkeypatch.setattr(classify_routes, "load_taxonomy", lambda path: {"path": path})
    monkeypatch.setattr(classify_routes, "load_rules", lambda *args, **kwargs: [])
    monkeypatch.setattr(classify_routes, "select_repos_for_classification", _fake_select)
    monkeypatch.setattr(classify_routes, "get_user_preferences", _fake_preferences)
    monkeypatch.setattr(classify_routes, "_resolve_classify_context", lambda *args, **kwargs: ("rules_only", False, None))
    monkeypatch.setattr(classify_routes, "_classify_repos_concurrent", _fake_classify)
    monkeypatch.setattr(classify_routes, "count_unclassified_repos", _fake_remaining)
    monkeypatch.setattr(classify_routes.cache, "invalidate_prefix", _fake_invalidate)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(github_client=object(), ai_client=object())
        )
    )
    response = _run(
        classify_routes.classify(
            request,
            ClassifyRequest(limit=2, force=False, include_readme=True, preference_user="demo"),
        )
    )

    assert response.total == 2
    assert response.classified == 1
    assert response.failed == 1
    assert response.remaining_unclassified == 5
    assert captured["select"] == (2, False)
    assert captured["classify"]["kwargs"]["concurrency"] == 1
    assert captured["classify"]["args"][6] is True
    assert captured["invalidate"] == ["stats", "repos"]


def test_settings_patch_validates_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    persisted: list[dict] = []

    def _fake_write_settings(updates: dict) -> None:
        persisted.append(updates)

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(settings_routes, "write_settings", _fake_write_settings)
    monkeypatch.setattr(settings_routes.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(
        settings_routes,
        "get_settings",
        lambda: SimpleNamespace(
            github_username="owner",
            github_target_username="target",
            github_usernames="owner,target",
            github_include_self=True,
            github_mode="merge",
            classify_mode="rules_only",
            auto_classify_after_sync=False,
            rules_json="[]",
            sync_cron="0 * * * *",
            sync_timeout=120,
        ),
    )

    with pytest.raises(HTTPException, match="No fields provided"):
        _run(settings_routes.update_settings(SettingsRequest()))

    response = _run(
        settings_routes.update_settings(
            SettingsRequest(github_mode="group", sync_timeout=300, auto_classify_after_sync=True)
        )
    )
    assert persisted == [
        {
            "GITHUB_MODE": "group",
            "SYNC_TIMEOUT": 300,
            "AUTO_CLASSIFY_AFTER_SYNC": True,
        }
    ]
    assert response.github_mode == "merge"
    assert response.sync_timeout == 120


def test_user_routes_patch_and_feedback_normalize_user(
    disable_limiters: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated_calls: list[tuple] = []
    feedback_calls: list[dict] = []

    async def _fake_update_preferences(user_id: str, tag_mapping=None, rule_priority=None) -> dict:
        updated_calls.append((user_id, tag_mapping, rule_priority))
        return {
            "user_id": user_id,
            "tag_mapping": tag_mapping or {},
            "rule_priority": rule_priority or {},
            "updated_at": "2026-03-07T00:00:00+00:00",
        }

    async def _fake_feedback(**kwargs) -> None:
        feedback_calls.append(kwargs)

    monkeypatch.setattr(user_routes, "update_user_preferences", _fake_update_preferences)
    monkeypatch.setattr(user_routes, "record_user_feedback_event", _fake_feedback)

    preference_response = _run(
        user_routes.patch_preferences(
            "   ",
            UserPreferencesRequest(tag_mapping={"ai": "llm"}, rule_priority={"r1": 1}),
        )
    )
    assert preference_response.user_id == "global"
    assert updated_calls == [("global", {"ai": "llm"}, {"r1": 1})]

    feedback_response = _run(
        user_routes.feedback_search(
            SimpleNamespace(),
            SearchFeedbackRequest(
                user_id="   ",
                query="agents",
                results_count=3,
                selected_tags=["AI"],
                category="ai",
                subcategory="agent",
            ),
        )
    )
    assert feedback_response.ok is True
    assert feedback_calls[0]["user_id"] == user_routes.PUBLIC_FEEDBACK_USER_ID
    assert feedback_calls[0]["event_type"] == "search"
    assert feedback_calls[0]["update_profile"] is False

    click_response = _run(
        user_routes.feedback_click(
            SimpleNamespace(),
            ClickFeedbackRequest(user_id="demo", full_name="owner/repo", query="agents"),
        )
    )
    assert click_response.ok is True
    assert feedback_calls[1]["event_type"] == "click"
    assert feedback_calls[1]["full_name"] == "owner/repo"
    assert feedback_calls[1]["user_id"] == user_routes.PUBLIC_FEEDBACK_USER_ID
    assert feedback_calls[1]["update_profile"] is False


def test_repos_query_override_and_readme_paths(
    admin_token_env: None,
    disable_limiters: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {"list": None, "cache_set": None, "quality": None, "override": None, "record": []}

    async def _fake_cache_get(key: str):
        del key
        return None

    async def _fake_cache_set(key: str, payload: dict, ttl: int) -> None:
        captured["cache_set"] = (key, payload, ttl)

    async def _fake_interest(user_id: str) -> dict:
        captured["interest_user_id"] = user_id
        return {"user_id": user_id, "topic_scores": {"ai": 0.9}}

    async def _fake_list_repos(**kwargs):
        captured["list"] = kwargs
        return SimpleNamespace(
            total=1,
            items=[_repo_payload()],
            has_more=False,
            next_offset=None,
            pagination_limited=False,
        )

    async def _fake_quality(**kwargs) -> None:
        captured["quality"] = kwargs

    async def _fake_update_override(full_name: str, updates: dict) -> bool:
        captured["override"] = (full_name, updates)
        return True

    async def _fake_invalidate(prefix: str) -> None:
        captured.setdefault("invalidate", []).append(prefix)

    async def _fake_get_repo(full_name: str):
        return _repo_payload(full_name)

    async def _fake_record_readme_fetch(full_name: str, summary: str | None, success: bool) -> None:
        captured["record"].append((full_name, summary, success))

    class _FakeGitHubClient:
        async def fetch_readme_summary(self, full_name: str) -> str:
            return f"summary for {full_name}"

    monkeypatch.setattr(repos_routes.cache, "get", _fake_cache_get)
    monkeypatch.setattr(repos_routes.cache, "set", _fake_cache_set)
    monkeypatch.setattr(repos_routes.cache, "invalidate_prefix", _fake_invalidate)
    monkeypatch.setattr(repos_routes, "get_user_interest_profile", _fake_interest)
    monkeypatch.setattr(repos_routes, "list_repos", _fake_list_repos)
    monkeypatch.setattr(repos_routes, "_add_quality_metrics", _fake_quality)
    monkeypatch.setattr(repos_routes, "update_override", _fake_update_override)
    monkeypatch.setattr(repos_routes, "get_repo", _fake_get_repo)
    monkeypatch.setattr(repos_routes, "record_readme_fetch", _fake_record_readme_fetch)

    list_response = _run(
        repos_routes.repos(
            SimpleNamespace(),
            q=" agents ",
            min_stars=None,
            tags="beta, alpha, alpha, ,gamma",
            tag_mode="or",
            sort="relevance",
            user_id="   ",
            limit=10,
            offset=5,
        )
    )
    assert list_response.total == 1
    assert list_response.has_more is False
    assert list_response.next_offset is None
    assert captured["list"]["q"] == "agents"
    assert captured["list"]["tags"] == ["alpha", "beta", "gamma"]
    assert captured["interest_user_id"] == "global"
    assert captured["quality"] == {"search_total": 1, "search_zero_result_total": 0}
    assert captured["cache_set"][1]["total"] == 1
    assert captured["cache_set"][1]["has_more"] is False

    detail_response = _run(repos_routes.repo_detail("owner/repo"))
    assert detail_response.full_name == "owner/repo"

    dependency_calls = _dependency_calls(repos_routes.router, "/repos/{full_name:path}/override")
    assert require_admin in dependency_calls

    override_response = _run(
        repos_routes.repo_override(
            "owner/repo",
            OverrideRequest(category="ai", tags=["tag-a", "", "tag-b"], tag_ids=["id-a", ""], note="memo"),
        )
    )
    assert override_response.updated is True
    assert captured["override"] == (
        "owner/repo",
        {"category": "ai", "tags": ["tag-a", "tag-b"], "tag_ids": ["id-a"], "note": "memo"},
    )

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(github_client=_FakeGitHubClient())))
    readme_response = _run(repos_routes.repo_readme("owner/repo", request))
    assert readme_response.updated is True
    assert readme_response.summary == "summary for owner/repo"
    assert captured["record"] == [("owner/repo", "summary for owner/repo", True)]


def test_repos_query_skips_interest_profile_for_non_relevance(
    disable_limiters: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"interest": False}

    async def _fake_cache_get(key: str):
        del key
        return None

    async def _fake_cache_set(key: str, payload: dict, ttl: int) -> None:
        del key, payload, ttl

    async def _fake_interest(user_id: str) -> dict:
        called["interest"] = True
        return {"user_id": user_id, "topic_scores": {"ai": 1.0}}

    async def _fake_list_repos(**kwargs):
        del kwargs
        return SimpleNamespace(
            total=0,
            items=[],
            has_more=False,
            next_offset=None,
            pagination_limited=False,
        )

    monkeypatch.setattr(repos_routes.cache, "get", _fake_cache_get)
    monkeypatch.setattr(repos_routes.cache, "set", _fake_cache_set)
    monkeypatch.setattr(repos_routes, "get_user_interest_profile", _fake_interest)
    monkeypatch.setattr(repos_routes, "list_repos", _fake_list_repos)

    response = _run(
        repos_routes.repos(
            SimpleNamespace(),
            q=None,
            min_stars=None,
            tags=None,
            tag_mode="or",
            sort="stars",
            user_id="demo",
            limit=10,
            offset=0,
        )
    )

    assert response.total == 0
    assert called["interest"] is False


def test_quality_metrics_endpoint_exposes_db_lock_counters(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_quality_metrics() -> dict:
        return {
            "classification_total": 0,
            "search_total": 0,
            "db_lock_conflict_total": 3,
            "db_lock_retry_total": 2,
            "db_lock_retry_exhausted_total": 1,
        }

    monkeypatch.setattr(stats_routes, "_get_quality_metrics", _fake_quality_metrics)

    response = _run(stats_routes.quality_metrics_endpoint())

    assert response["db_lock_conflict_total"] == 3
    assert response["db_lock_retry_total"] == 2
    assert response["db_lock_retry_exhausted_total"] == 1


def test_repos_detail_and_override_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _missing_repo(full_name: str):
        del full_name
        return None

    async def _update_override(full_name: str, updates: dict) -> bool:
        del full_name, updates
        return False

    monkeypatch.setattr(repos_routes, "get_repo", _missing_repo)
    monkeypatch.setattr(repos_routes, "update_override", _update_override)

    with pytest.raises(HTTPException, match="Repo not found"):
        _run(repos_routes.repo_detail("missing/repo"))

    with pytest.raises(HTTPException, match="category cannot be empty"):
        _run(repos_routes.repo_override("missing/repo", OverrideRequest(category="   ")))

    with pytest.raises(HTTPException, match="No fields provided"):
        _run(repos_routes.repo_override("missing/repo", OverrideRequest()))


def test_task_status_returns_404_for_missing_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _missing_task(task_id: str):
        del task_id
        return None

    monkeypatch.setattr(tasks_routes, "get_task", _missing_task)

    with pytest.raises(HTTPException, match="Task not found"):
        _run(tasks_routes.task_status("expired-task-id"))


def test_classify_batch_uses_batch_ai_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {
        "batch_calls": [],
        "single_calls": [],
        "bulk_updates": None,
        "quality": None,
        "failed_names": [],
    }

    class _FakeEngine:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def prepare_classification(self, repo: dict) -> PreparedClassification:
            pending = PendingAIClassification(
                reason="batch-ai",
                top_candidate=None,
                rule_candidates=[],
                ai_input={
                    "full_name": repo["full_name"],
                    "name": repo["name"],
                    "description": repo["description"],
                    "topics": repo["topics"],
                    "rule_candidates": [],
                },
            )
            return PreparedClassification(pending_ai=pending)

        def outcome_from_ai_result(
            self,
            ai_result: dict,
            reason: str,
            rule_candidates: list,
        ) -> ClassificationOutcome:
            del reason, rule_candidates
            return ClassificationOutcome(
                result=ai_result,
                source="ai",
                reason="batch-ai",
                rule_candidates=[],
            )

        def fallback_outcome(self, top_candidate, rule_candidates):
            del top_candidate, rule_candidates
            raise AssertionError("fallback_outcome should not be used in batch success path")

    class _FakeAIClient:
        async def classify_repos_with_retry(self, repos: list, taxonomy: dict, retries: int = 2):
            captured["batch_calls"].append((repos, taxonomy, retries))
            return [
                {
                    "category": "ai",
                    "subcategory": "agents",
                    "confidence": 0.92,
                    "tags": ["Agent"],
                    "tag_ids": ["ai.agent"],
                    "reason": "batched",
                    "summary_zh": "批量分类结果",
                    "keywords": ["agent", "automation"],
                    "provider": "mock",
                    "model": "mock-model",
                }
                for _ in repos
            ]

        async def classify_repo_with_retry(self, repo: dict, taxonomy: dict, retries: int = 2):
            captured["single_calls"].append((repo, taxonomy, retries))
            raise AssertionError("single-item AI fallback should not be used when batch succeeds")

    async def _fake_update_bulk(items: list[dict]) -> int:
        captured["bulk_updates"] = items
        return len(items)

    async def _fake_quality(**kwargs) -> None:
        captured["quality"] = kwargs

    async def _fake_increment(full_names: list[str]) -> None:
        captured["failed_names"] = full_names

    async def _fake_readme_fetches(entries: list[dict]) -> None:
        del entries

    monkeypatch.setattr(classify_routes, "ClassificationEngine", _FakeEngine)
    monkeypatch.setattr(classify_routes, "update_classifications_bulk", _fake_update_bulk)
    monkeypatch.setattr(classify_routes, "_add_quality_metrics", _fake_quality)
    monkeypatch.setattr(classify_routes, "increment_classify_fail_count", _fake_increment)
    monkeypatch.setattr(classify_routes, "record_readme_fetches", _fake_readme_fetches)

    repos = [_repo_payload("owner/repo-1"), _repo_payload("owner/repo-2")]
    classified, failed = _run(
        classify_routes._classify_repos_batch(
            repos,
            data={"tag_id_to_name": {"ai.agent": "Agent"}},
            rules=[],
            classify_mode="hybrid",
            use_ai=True,
            preference={},
            include_readme=False,
            github_client=SimpleNamespace(),
            ai_client=_FakeAIClient(),
            task_id="task-1",
        )
    )

    assert classified == 2
    assert failed == 0
    assert len(captured["batch_calls"]) == 1
    assert captured["single_calls"] == []
    assert len(captured["bulk_updates"]) == 2
    assert captured["quality"] == {
        "classification_total": 2,
        "rule_hit_total": 0,
        "ai_fallback_total": 0,
        "empty_tag_total": 0,
        "uncategorized_total": 0,
    }
    assert captured["failed_names"] == []


def test_resolve_request_id_uses_explicit_value_and_falls_back_to_uuid() -> None:
    assert resolve_request_id("demo-request-id") == "demo-request-id"
    generated = resolve_request_id("   ")
    assert str(uuid.UUID(generated)) == generated


def test_bind_log_context_sets_and_resets_ids() -> None:
    assert get_request_id() is None
    assert get_task_id() is None

    with bind_log_context(request_id="req-1", task_id="task-1"):
        assert get_request_id() == "req-1"
        assert get_task_id() == "task-1"

    assert get_request_id() is None
    assert get_task_id() is None


def test_create_observed_task_propagates_request_and_task_context() -> None:
    async def _capture() -> tuple[str | None, str | None]:
        return get_request_id(), get_task_id()

    async def _run_capture() -> tuple[str | None, str | None]:
        with bind_log_context(request_id="req-outer"):
            task = create_observed_task(_capture(), task_id="task-outer")
            return await task

    assert _run(_run_capture()) == ("req-outer", "task-outer")
