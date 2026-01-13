import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    github_username: str
    github_target_username: str
    github_usernames: str
    github_include_self: bool
    github_mode: str
    github_token: str
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


def get_settings() -> Settings:
    from .settings_store import read_settings

    overrides = {}
    try:
        overrides = read_settings()
    except Exception:
        overrides = {}

    def pick(key: str, default: str) -> str:
        if key in overrides:
            value = overrides.get(key)
            return default if value is None else str(value)
        return os.getenv(key, default)

    def pick_nonempty(key: str, default: str) -> str:
        value = pick(key, default)
        return value if str(value).strip() else default

    def pick_int(key: str, default: int) -> int:
        if key in overrides:
            value = overrides.get(key)
            if value is None:
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        try:
            return int(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default

    def pick_float(key: str, default: float) -> float:
        if key in overrides:
            value = overrides.get(key)
            if value is None:
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        try:
            return float(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default

    def pick_bool(key: str, default: bool) -> bool:
        if key in overrides:
            value = overrides.get(key)
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("1", "true", "yes", "on")
        return os.getenv(key, str(default)).lower() in ("1", "true", "yes", "on")

    return Settings(
        github_username=pick("GITHUB_USERNAME", ""),
        github_target_username=pick("GITHUB_TARGET_USERNAME", ""),
        github_usernames=pick("GITHUB_USERNAMES", ""),
        github_include_self=pick_bool("GITHUB_INCLUDE_SELF", False),
        github_mode=pick("GITHUB_MODE", "merge"),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        ai_provider=pick("AI_PROVIDER", "none"),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_model=pick("AI_MODEL", ""),
        ai_base_url=pick("AI_BASE_URL", ""),
        ai_headers_json=pick("AI_HEADERS_JSON", ""),
        ai_temperature=pick_float("AI_TEMPERATURE", 0.2),
        ai_max_tokens=pick_int("AI_MAX_TOKENS", 500),
        ai_timeout=pick_int("AI_TIMEOUT", 30),
        ai_taxonomy_path=pick_nonempty(
            "AI_TAXONOMY_PATH", str(API_ROOT / "config" / "taxonomy.yaml")
        ),
        rules_json=pick("RULES_JSON", ""),
        sync_cron=pick("SYNC_CRON", "0 */6 * * *"),
        sync_timeout=pick_int("SYNC_TIMEOUT", 30),
        database_url=os.getenv("DATABASE_URL", "sqlite:////data/app.db"),
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
