import logging
import os
import secrets
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from fastapi import Response

logger = logging.getLogger("starsorty.security")

_RUNTIME_ENV_KEYS = ("APP_ENV", "ENVIRONMENT", "PYTHON_ENV", "ENV")
_PRODUCTION_VALUES = {"production", "prod"}
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_INVALID_PUBLIC_API_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "api", "web"}

ADMIN_SESSION_COOKIE_NAME = "starsorty_admin_session"
ADMIN_CSRF_COOKIE_NAME = "starsorty_admin_csrf"
_ADMIN_COOKIE_SAMESITE = "lax"


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


def get_admin_session_ttl_seconds() -> int:
    raw_value = os.getenv("ADMIN_SESSION_TTL_HOURS", "12").strip()
    try:
        hours = int(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid ADMIN_SESSION_TTL_HOURS=%r, fallback to 12 hours",
            raw_value,
        )
        hours = 12
    hours = max(1, hours)
    return hours * 3600


def is_unauthenticated_admin_dev_override_requested() -> bool:
    return os.getenv("ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV", "").strip().lower() in _TRUTHY_VALUES


def allow_unauthenticated_admin_in_dev() -> bool:
    return is_unauthenticated_admin_dev_override_requested() and get_runtime_env() not in _PRODUCTION_VALUES


def admin_request_requires_csrf(method: str) -> bool:
    return method.upper() in _UNSAFE_HTTP_METHODS


def get_admin_cookie_secure() -> bool:
    return get_runtime_env() in _PRODUCTION_VALUES


def validate_public_api_base_url(public_api_base_url_raw: str | None = None) -> None:
    raw_value = public_api_base_url_raw
    if raw_value is None:
        raw_value = os.getenv("NEXT_PUBLIC_API_BASE_URL", "")
    raw_value = raw_value.strip()
    if not raw_value:
        return
    if raw_value.startswith("/"):
        if raw_value.startswith("//"):
            raise RuntimeError(
                "NEXT_PUBLIC_API_BASE_URL must be a relative path like /api or an https:// URL in production."
            )
        return

    parsed = urlparse(raw_value)
    hostname = (parsed.hostname or "").strip().lower()
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(
            "NEXT_PUBLIC_API_BASE_URL must be a relative path like /api or an https:// URL in production."
        )
    if hostname in _INVALID_PUBLIC_API_HOSTS:
        raise RuntimeError(
            "NEXT_PUBLIC_API_BASE_URL cannot point to localhost or internal Docker hostnames in production. "
            "Use /api behind a same-site reverse proxy or an https:// public URL."
        )
    if parsed.scheme != "https":
        raise RuntimeError(
            "NEXT_PUBLIC_API_BASE_URL must use https:// or a relative path like /api in production."
        )


def set_admin_auth_cookies(
    response: Response,
    *,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = get_admin_session_ttl_seconds()
    secure = get_admin_cookie_secure()
    response.set_cookie(
        ADMIN_SESSION_COOKIE_NAME,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=_ADMIN_COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite=_ADMIN_COOKIE_SAMESITE,
        path="/",
    )


def clear_admin_auth_cookies(response: Response) -> None:
    response.delete_cookie(ADMIN_SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(ADMIN_CSRF_COOKIE_NAME, path="/")


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
    insecure_admin_override = is_unauthenticated_admin_dev_override_requested()
    cors_value = cors_origins_raw
    if cors_value is None:
        cors_value = os.getenv("CORS_ORIGINS", "http://localhost:1234")
    origins, allow_credentials = resolve_cors_policy(cors_value)
    logger.info(
        "Security self-check: env=%s production_mode=%s admin_token_configured=%s insecure_admin_override=%s cors_origins=%s cors_allow_credentials=%s",
        status.runtime_env,
        status.production_mode,
        status.admin_token_configured,
        insecure_admin_override,
        origins,
        allow_credentials,
    )
    if status.production_mode and insecure_admin_override:
        raise RuntimeError(
            "ALLOW_UNAUTHENTICATED_ADMIN_IN_DEV cannot be enabled in production mode."
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
    if status.production_mode:
        validate_public_api_base_url()
