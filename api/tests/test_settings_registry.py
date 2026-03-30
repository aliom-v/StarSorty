from pathlib import Path

import pytest

from api.app.config import clear_settings_cache, get_settings
from api.app.settings_store import read_settings, write_settings


def _sqlite_url(path: Path) -> str:
    return f"sqlite:////{str(path).lstrip('/')}"


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_settings_store_coerces_and_ignores_env_only_keys(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "settings.db"
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("AI_PROVIDER", "custom")
    monkeypatch.setenv("AI_TAXONOMY_PATH", str(tmp_path / "taxonomy.yaml"))

    write_settings(
        {
            "SYNC_TIMEOUT": "12",
            "GITHUB_INCLUDE_SELF": "true",
            "CLASSIFY_MODE": "RULES_THEN_AI",
            "AI_PROVIDER": "openai",
        }
    )

    overrides = read_settings()
    settings = get_settings()

    assert overrides["SYNC_TIMEOUT"] == 12
    assert overrides["GITHUB_INCLUDE_SELF"] is True
    assert overrides["CLASSIFY_MODE"] == "rules_then_ai"
    assert "AI_PROVIDER" not in overrides
    assert settings.sync_timeout == 12
    assert settings.github_include_self is True
    assert settings.classify_mode == "rules_then_ai"
    assert settings.ai_provider == "custom"


def test_invalid_settings_override_falls_back_to_defaults(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "settings-invalid.db"
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("AI_TAXONOMY_PATH", str(tmp_path / "taxonomy.yaml"))

    write_settings(
        {
            "CLASSIFY_MODE": "invalid-mode",
            "SYNC_TIMEOUT": 0,
            "GITHUB_MODE": "unknown",
        }
    )

    settings = get_settings()

    assert settings.classify_mode == "ai_only"
    assert settings.sync_timeout == 30
    assert settings.github_mode == "merge"


def test_get_settings_reuses_cached_snapshot_until_store_revision_changes(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "settings-cache.db"
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("AI_TAXONOMY_PATH", str(tmp_path / "taxonomy.yaml"))

    first = get_settings()
    second = get_settings()

    assert first is second

    write_settings({"SYNC_TIMEOUT": 42})

    refreshed = get_settings()
    assert refreshed is not first
    assert refreshed.sync_timeout == 42
    assert get_settings() is refreshed


def test_get_settings_rebuilds_snapshot_when_env_values_change(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "settings-env.db"
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("AI_TAXONOMY_PATH", str(tmp_path / "taxonomy.yaml"))
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    first = get_settings()

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    refreshed = get_settings()

    assert refreshed is not first
    assert refreshed.log_level == "DEBUG"


def test_blank_ai_taxonomy_path_uses_builtin_default(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "settings-taxonomy-default.db"
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("AI_TAXONOMY_PATH", "")

    settings = get_settings()

    assert settings.ai_taxonomy_path == str(
        Path(__file__).resolve().parents[1] / "config" / "taxonomy.yaml"
    )
