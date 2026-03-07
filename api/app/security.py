import logging
import os
import secrets
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("starsorty.security")

_RUNTIME_ENV_KEYS = ("APP_ENV", "ENVIRONMENT", "PYTHON_ENV", "ENV")
_PRODUCTION_VALUES = {"production", "prod"}


@dataclass(frozen=True)
class SecurityBaselineStatus:
    runtime_env: str
    production_mode: bool
    admin_token_configured: bool


def get_runtime_env() -> str:
    for key in _RUNTIME_ENV_KEYS:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip().lower()
    return "development"


def get_admin_token() -> str:
    return os.getenv("ADMIN_TOKEN", "").strip()


def parse_cors_origins(cors_origins_raw: str) -> List[str]:
    return [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]


def resolve_cors_policy(cors_origins_raw: str) -> Tuple[List[str], bool]:
    origins = parse_cors_origins(cors_origins_raw)
    allow_credentials = bool(origins) and "*" not in origins
    return origins, allow_credentials


def is_admin_token_valid(candidate: str | None) -> bool:
    admin_token = get_admin_token()
    if not admin_token or not candidate:
        return False
    return secrets.compare_digest(candidate, admin_token)


def get_security_baseline_status() -> SecurityBaselineStatus:
    runtime_env = get_runtime_env()
    return SecurityBaselineStatus(
        runtime_env=runtime_env,
        production_mode=runtime_env in _PRODUCTION_VALUES,
        admin_token_configured=bool(get_admin_token()),
    )


def get_security_baseline_payload() -> Dict[str, Any]:
    return asdict(get_security_baseline_status())


def validate_security_baseline(cors_origins_raw: str | None = None) -> None:
    status = get_security_baseline_status()
    cors_value = cors_origins_raw
    if cors_value is None:
        cors_value = os.getenv("CORS_ORIGINS", "http://localhost:1234")
    origins, allow_credentials = resolve_cors_policy(cors_value)
    logger.info(
        "Security self-check: env=%s production_mode=%s admin_token_configured=%s cors_origins=%s cors_allow_credentials=%s",
        status.runtime_env,
        status.production_mode,
        status.admin_token_configured,
        origins,
        allow_credentials,
    )
    if status.production_mode and not status.admin_token_configured:
        raise RuntimeError(
            "ADMIN_TOKEN is required in production mode. "
            "Set ADMIN_TOKEN when APP_ENV/ENVIRONMENT/PYTHON_ENV/ENV is production."
        )
    if status.production_mode and (not origins or "*" in origins):
        raise RuntimeError(
            "CORS_ORIGINS must be an explicit origin list in production. "
            "Wildcard (*) or empty values are not allowed."
        )
