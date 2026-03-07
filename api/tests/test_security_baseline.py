import asyncio
import pytest

from api.app import security as security_mod
from api.app.routes import export as export_routes
from api.app.routes import health as health_routes


def _clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("APP_ENV", "ENVIRONMENT", "PYTHON_ENV", "ENV"):
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

    security_mod.validate_security_baseline()


def test_validate_security_baseline_allows_without_admin_token_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    security_mod.validate_security_baseline()


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
        return b"PK\x05\x06" + b"\x00" * 18

    monkeypatch.setattr(export_routes, "iter_repos_for_export", _fake_repo_iter)
    monkeypatch.setattr(export_routes, "generate_obsidian_zip_streaming", _fake_zip)

    response = asyncio.run(export_routes.export_obsidian(request=object()))
    assert response.status_code == 200
    assert response.media_type == "application/zip"
    assert response.body.startswith(b"PK")


def test_health_security_fields_only_visible_with_valid_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "secret")

    public_payload = asyncio.run(health_routes.health(None))
    assert public_payload == {"status": "ok"}

    invalid_payload = asyncio.run(health_routes.health("wrong"))
    assert invalid_payload == {"status": "ok"}

    admin_payload = asyncio.run(health_routes.health("secret"))
    assert admin_payload == {
        "status": "ok",
        "security": {
            "runtime_env": "production",
            "production_mode": True,
            "admin_token_configured": True,
        },
    }
