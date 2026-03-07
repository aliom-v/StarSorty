import asyncio
from types import SimpleNamespace

import pytest

from api.app.deps import require_admin
from api.app.routes import repos as repos_routes
from api.app.routes import settings as settings_routes
from api.app.routes import user as user_routes


def _dependency_calls(router, path: str) -> list:
    route = next(route for route in router.routes if getattr(route, "path", None) == path)
    return [dependency.dependency for dependency in route.dependencies]


@pytest.fixture
def admin_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret")


def test_settings_route_requires_admin_and_returns_settings(
    admin_token_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings_routes,
        "get_settings",
        lambda: SimpleNamespace(
            github_username="owner",
            github_target_username="owner",
            github_usernames="owner",
            github_include_self=True,
            github_mode="merge",
            classify_mode="rules_then_ai",
            auto_classify_after_sync=True,
            rules_json="[]",
            sync_cron="0 * * * *",
            sync_timeout=600,
        ),
    )

    dependency_calls = _dependency_calls(settings_routes.router, "/settings")
    assert require_admin in dependency_calls

    response = asyncio.run(settings_routes.settings())
    assert response.github_username == "owner"
    assert response.github_mode == "merge"


def test_client_settings_route_remains_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings_routes,
        "get_settings",
        lambda: SimpleNamespace(
            github_mode="merge",
            classify_mode="rules_then_ai",
            auto_classify_after_sync=True,
            rules_json="[]",
        ),
    )
    monkeypatch.setattr(settings_routes, "load_rules", lambda *args, **kwargs: [])
    monkeypatch.setattr(settings_routes, "_resolve_classify_context_for_validation", lambda current, rules: None)

    dependency_calls = _dependency_calls(settings_routes.router, "/api/config/client-settings")
    assert require_admin not in dependency_calls

    response = asyncio.run(settings_routes.client_settings())
    assert response.model_dump() == {
        "github_mode": "merge",
        "classify_mode": "rules_then_ai",
        "auto_classify_after_sync": True,
    }


def test_preference_and_interest_routes_require_admin_and_return_data(
    admin_token_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_preferences(user_id: str) -> dict:
        return {
            "user_id": user_id,
            "tag_mapping": {"ai": "llm"},
            "rule_priority": {"rules": 10},
            "updated_at": "2026-03-07T00:00:00+00:00",
        }

    async def _fake_interest(user_id: str) -> dict:
        return {
            "user_id": user_id,
            "topic_scores": {"ai": 0.8},
            "top_topics": [{"topic": "ai", "score": 0.8}],
            "updated_at": "2026-03-07T00:00:00+00:00",
        }

    monkeypatch.setattr(user_routes, "get_user_preferences", _fake_preferences)
    monkeypatch.setattr(user_routes, "get_user_interest_profile", _fake_interest)

    preference_dependency_calls = _dependency_calls(user_routes.router, "/preferences/{user_id}")
    interest_dependency_calls = _dependency_calls(user_routes.router, "/interest/{user_id}")
    assert require_admin in preference_dependency_calls
    assert require_admin in interest_dependency_calls

    preference = asyncio.run(user_routes.get_preferences("demo"))
    interest = asyncio.run(user_routes.interest_profile("demo"))
    assert preference.user_id == "demo"
    assert interest.user_id == "demo"


def test_failed_repos_route_requires_admin_and_returns_items(
    admin_token_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_failed(min_fail_count: int):
        return [
            {
                "full_name": "owner/repo",
                "name": "repo",
                "owner": "owner",
                "description": "demo",
                "language": "Python",
                "classify_fail_count": min_fail_count,
            }
        ]

    monkeypatch.setattr(repos_routes, "get_failed_repos", _fake_failed)

    dependency_calls = _dependency_calls(repos_routes.router, "/repos/failed")
    assert require_admin in dependency_calls

    response = asyncio.run(repos_routes.list_failed_repos_endpoint(min_fail_count=5))
    assert response.total == 1
    assert response.items[0].full_name == "owner/repo"
