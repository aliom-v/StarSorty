from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SettingKind = Literal["str", "bool", "int", "float"]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    kind: SettingKind
    default: Any
    env_only: bool = False
    nonempty: bool = False
    choices: tuple[str, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    lowercase: bool = False


SETTINGS_REGISTRY: dict[str, SettingSpec] = {
    "GITHUB_USERNAME": SettingSpec("GITHUB_USERNAME", "str", ""),
    "GITHUB_TARGET_USERNAME": SettingSpec("GITHUB_TARGET_USERNAME", "str", ""),
    "GITHUB_USERNAMES": SettingSpec("GITHUB_USERNAMES", "str", ""),
    "GITHUB_INCLUDE_SELF": SettingSpec("GITHUB_INCLUDE_SELF", "bool", False),
    "GITHUB_MODE": SettingSpec(
        "GITHUB_MODE",
        "str",
        "merge",
        choices=("merge", "group"),
        lowercase=True,
    ),
    "GITHUB_TOKEN": SettingSpec("GITHUB_TOKEN", "str", "", env_only=True),
    "CLASSIFY_MODE": SettingSpec(
        "CLASSIFY_MODE",
        "str",
        "ai_only",
        choices=("rules_then_ai", "ai_only", "rules_only"),
        lowercase=True,
    ),
    "AUTO_CLASSIFY_AFTER_SYNC": SettingSpec(
        "AUTO_CLASSIFY_AFTER_SYNC",
        "bool",
        True,
    ),
    "AI_PROVIDER": SettingSpec(
        "AI_PROVIDER",
        "str",
        "none",
        env_only=True,
        nonempty=True,
        lowercase=True,
    ),
    "AI_API_KEY": SettingSpec("AI_API_KEY", "str", "", env_only=True),
    "AI_MODEL": SettingSpec("AI_MODEL", "str", "", env_only=True),
    "AI_BASE_URL": SettingSpec("AI_BASE_URL", "str", "", env_only=True),
    "AI_HEADERS_JSON": SettingSpec("AI_HEADERS_JSON", "str", "", env_only=True),
    "AI_TEMPERATURE": SettingSpec("AI_TEMPERATURE", "float", 0.2, env_only=True),
    "AI_MAX_TOKENS": SettingSpec(
        "AI_MAX_TOKENS",
        "int",
        500,
        env_only=True,
        minimum=1,
    ),
    "AI_TIMEOUT": SettingSpec(
        "AI_TIMEOUT",
        "int",
        30,
        env_only=True,
        minimum=1,
    ),
    "AI_TAXONOMY_PATH": SettingSpec(
        "AI_TAXONOMY_PATH",
        "str",
        "",
        env_only=True,
        nonempty=True,
    ),
    "RULES_JSON": SettingSpec("RULES_JSON", "str", ""),
    "SYNC_CRON": SettingSpec("SYNC_CRON", "str", "0 */6 * * *", nonempty=True),
    "SYNC_TIMEOUT": SettingSpec("SYNC_TIMEOUT", "int", 30, minimum=1, maximum=3600),
    "DATABASE_URL": SettingSpec(
        "DATABASE_URL",
        "str",
        "sqlite:////data/app.db",
        env_only=True,
        nonempty=True,
    ),
    "CORS_ORIGINS": SettingSpec(
        "CORS_ORIGINS",
        "str",
        "http://localhost:1234",
        env_only=True,
        nonempty=True,
    ),
    "LOG_LEVEL": SettingSpec(
        "LOG_LEVEL",
        "str",
        "INFO",
        env_only=True,
        nonempty=True,
    ),
}

OVERRIDABLE_SETTING_KEYS = tuple(
    key for key, spec in SETTINGS_REGISTRY.items() if not spec.env_only
)


def get_setting_spec(key: str) -> SettingSpec | None:
    return SETTINGS_REGISTRY.get(str(key or "").strip().upper())


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def coerce_setting_value(spec: SettingSpec, value: Any) -> Any:
    if spec.kind == "bool":
        coerced = _coerce_bool(value, bool(spec.default))
    elif spec.kind == "int":
        coerced = _coerce_int(value, int(spec.default))
    elif spec.kind == "float":
        coerced = _coerce_float(value, float(spec.default))
    else:
        coerced = _coerce_str(value, str(spec.default))

    if spec.kind == "str":
        text = str(coerced).strip()
        if spec.lowercase:
            text = text.lower()
        if spec.nonempty and not text:
            text = str(spec.default)
            if spec.lowercase:
                text = text.lower()
        if spec.choices and text not in spec.choices:
            return spec.default
        return text

    if spec.kind in ("int", "float"):
        numeric = coerced
        if spec.minimum is not None and numeric < spec.minimum:
            return spec.default
        if spec.maximum is not None and numeric > spec.maximum:
            return spec.default
        return numeric

    return coerced

