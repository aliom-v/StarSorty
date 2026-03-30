import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .settings_meta import SETTINGS_REGISTRY, coerce_setting_value

logger = logging.getLogger("starsorty.config")
REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

_settings_cache_lock = threading.RLock()
_settings_cache: "Settings | None" = None
_settings_cache_env_signature: tuple[tuple[str, str | None], ...] | None = None
_settings_cache_store_revision: int | None = None


@dataclass(frozen=True)
class Settings:
    github_username: str
    github_target_username: str
    github_usernames: str
    github_include_self: bool
    github_mode: str
    github_token: str
    classify_mode: str
    auto_classify_after_sync: bool
    ai_provider: str
    ai_api_key: str
    ai_model: str
    ai_base_url: str
    ai_headers_json: str
    ai_temperature: float
    ai_max_tokens: int
    ai_timeout: int
    ai_taxonomy_path: str
    rules_json: str
    sync_cron: str
    sync_timeout: int
    database_url: str
    cors_origins: str
    log_level: str


def _current_settings_env_signature() -> tuple[tuple[str, str | None], ...]:
    return tuple((key, os.getenv(key)) for key in SETTINGS_REGISTRY)


def clear_settings_cache() -> None:
    global _settings_cache, _settings_cache_env_signature, _settings_cache_store_revision
    with _settings_cache_lock:
        _settings_cache = None
        _settings_cache_env_signature = None
        _settings_cache_store_revision = None


def _read_settings_overrides() -> dict[str, Any]:
    from .settings_store import read_settings

    try:
        return read_settings()
    except Exception as exc:
        logger.warning("Failed to read settings overrides: %s", exc)
        return {}


def _build_settings(overrides: dict[str, Any]) -> Settings:
    def resolve(key: str) -> object:
        spec = SETTINGS_REGISTRY[key]
        raw_value = overrides.get(key) if not spec.env_only and key in overrides else os.getenv(key)
        if key == "AI_TAXONOMY_PATH" and (
            raw_value is None or not str(raw_value).strip()
        ):
            raw_value = str(API_ROOT / "config" / "taxonomy.yaml")
        if raw_value is None:
            raw_value = spec.default
        return coerce_setting_value(spec, raw_value)

    return Settings(
        github_username=str(resolve("GITHUB_USERNAME")),
        github_target_username=str(resolve("GITHUB_TARGET_USERNAME")),
        github_usernames=str(resolve("GITHUB_USERNAMES")),
        github_include_self=bool(resolve("GITHUB_INCLUDE_SELF")),
        github_mode=str(resolve("GITHUB_MODE")),
        github_token=str(resolve("GITHUB_TOKEN")),
        classify_mode=str(resolve("CLASSIFY_MODE")),
        auto_classify_after_sync=bool(resolve("AUTO_CLASSIFY_AFTER_SYNC")),
        ai_provider=str(resolve("AI_PROVIDER")),
        ai_api_key=str(resolve("AI_API_KEY")),
        ai_model=str(resolve("AI_MODEL")),
        ai_base_url=str(resolve("AI_BASE_URL")),
        ai_headers_json=str(resolve("AI_HEADERS_JSON")),
        ai_temperature=float(resolve("AI_TEMPERATURE")),
        ai_max_tokens=int(resolve("AI_MAX_TOKENS")),
        ai_timeout=int(resolve("AI_TIMEOUT")),
        ai_taxonomy_path=str(resolve("AI_TAXONOMY_PATH")),
        rules_json=str(resolve("RULES_JSON")),
        sync_cron=str(resolve("SYNC_CRON")),
        sync_timeout=int(resolve("SYNC_TIMEOUT")),
        database_url=str(resolve("DATABASE_URL")),
        cors_origins=str(resolve("CORS_ORIGINS")),
        log_level=str(resolve("LOG_LEVEL")),
    )


def get_settings() -> Settings:
    from .settings_store import get_settings_store_revision

    global _settings_cache, _settings_cache_env_signature, _settings_cache_store_revision

    env_signature = _current_settings_env_signature()
    store_revision = get_settings_store_revision()

    with _settings_cache_lock:
        if (
            _settings_cache is not None
            and _settings_cache_env_signature == env_signature
            and _settings_cache_store_revision == store_revision
        ):
            return _settings_cache

    settings = _build_settings(_read_settings_overrides())

    with _settings_cache_lock:
        _settings_cache = settings
        _settings_cache_env_signature = env_signature
        _settings_cache_store_revision = store_revision
    return settings
