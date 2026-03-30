import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.app import deps as deps_mod
from api.app import security as security_mod
from api.app.routes import export as export_routes
from api.app.routes import health as health_routes


def _clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "APP_ENV",
        "ENVIRONMENT",
        "PYTHON_ENV",
        "ENV",
        "ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV",
    ):
        monkeypatch.delenv(key, raising=False)


def test_validate_security_baseline_raises_without_admin_token_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="ADMIN_TOKEN"):
        security_mod.validate_security_baseline()


def test_validate_security_baseline_allows_with_admin_token_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE_URL", "/api")

    security_mod.validate_security_baseline()


def test_validate_security_baseline_allows_without_admin_token_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    security_mod.validate_security_baseline()


def test_validate_security_baseline_rejects_dev_admin_override_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV", "1")

    with pytest.raises(RuntimeError, match="ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV"):
        security_mod.validate_security_baseline()


def test_require_admin_rejects_when_admin_token_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV", raising=False)
    monkeypatch.setattr(deps_mod, "_admin_token_warned", False)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(deps_mod.require_admin(SimpleNamespace(method="GET"), None, None, None))

    assert exc_info.value.status_code == 503
    assert "ADMIN_TOKEN" in str(exc_info.value.detail)


def test_require_admin_allows_explicit_dev_override_without_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV", "1")
    monkeypatch.setattr(deps_mod, "_admin_token_warned", False)

    asyncio.run(deps_mod.require_admin(SimpleNamespace(method="GET"), None, None, None))


def test_validate_security_baseline_rejects_wildcard_cors_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        security_mod.validate_security_baseline("*")


def test_validate_security_baseline_rejects_empty_cors_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        security_mod.validate_security_baseline("")


def test_validate_security_baseline_rejects_localhost_public_api_base_url_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:4321")

    with pytest.raises(RuntimeError, match="NEXT_PUBLIC_API_BASE_URL"):
        security_mod.validate_security_baseline("https://stars.example.com")


def test_validate_security_baseline_rejects_http_public_api_base_url_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE_URL", "http://stars-api.example.com")

    with pytest.raises(RuntimeError, match="NEXT_PUBLIC_API_BASE_URL"):
        security_mod.validate_security_baseline("https://stars.example.com")


def test_validate_security_baseline_allows_relative_public_api_base_url_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE_URL", "/api")

    security_mod.validate_security_baseline("https://stars.example.com")


def test_resolve_cors_policy_disables_credentials_for_wildcard() -> None:
    origins, allow_credentials = security_mod.resolve_cors_policy("*, http://localhost:1234")
    assert origins == ["*", "http://localhost:1234"]
    assert allow_credentials is False


def test_resolve_cors_policy_enables_credentials_for_explicit_origins() -> None:
    origins, allow_credentials = security_mod.resolve_cors_policy(
        "http://localhost:1234,https://starsorty.example.com"
    )
    assert origins == ["http://localhost:1234", "https://starsorty.example.com"]
    assert allow_credentials is True


def test_export_route_has_admin_dependency() -> None:
    route = next(
        route
        for route in export_routes.router.routes
        if getattr(route, "path", None) == "/export/obsidian"
    )
    dependency_calls = [dependency.dependency for dependency in route.dependencies]
    assert export_routes.require_admin in dependency_calls


def test_export_obsidian_direct_call_returns_zip_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(export_routes.limiter, "enabled", False)

    def _fake_repo_iter(*, language=None, tags=None):
        del language, tags
        return iter(())

    async def _fake_zip(repo_iter):
        del repo_iter
        yield b"PK\x05\x06"
        yield b"\x00" * 18

    async def _collect_streaming_body(response) -> bytes:
        chunks = bytearray()
        async for chunk in response.body_iterator:
            chunks.extend(chunk)
        return bytes(chunks)

    monkeypatch.setattr(export_routes, "iter_repos_for_export", _fake_repo_iter)
    monkeypatch.setattr(export_routes, "generate_obsidian_zip_streaming", _fake_zip)

    response = asyncio.run(export_routes.export_obsidian(request=object()))
    assert response.status_code == 200
    assert response.media_type == "application/zip"
    assert asyncio.run(_collect_streaming_body(response)).startswith(b"PK")


def test_health_security_fields_only_visible_with_valid_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")

    request = SimpleNamespace(method="GET")

    public_payload = asyncio.run(health_routes.health(request, None, None))
    assert public_payload == {"status": "ok"}

    invalid_payload = asyncio.run(health_routes.health(request, "wrong", None))
    assert invalid_payload == {"status": "ok"}

    admin_payload = asyncio.run(health_routes.health(request, "secret", None))
    assert admin_payload == {
        "status": "ok",
        "security": {
            "runtime_env": "production",
            "production_mode": True,
            "admin_token_configured": True,
        },
    }
