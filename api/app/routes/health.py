import secrets

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response

from ..db import (
    build_admin_session_expiry,
    create_admin_session,
    delete_admin_session,
    generate_admin_session_tokens,
    purge_expired_admin_sessions,
)
from ..deps import _admin_auth_failure_exception, require_admin, resolve_admin_auth_mode
from ..rate_limit import limiter, RATE_LIMIT_ADMIN
from ..schemas import AuthSessionRequest, AuthStatusResponse
from ..security import (
    ADMIN_SESSION_COOKIE_NAME,
    allow_unauthenticated_admin_in_dev,
    clear_admin_auth_cookies,
    get_admin_session_ttl_seconds,
    get_admin_token,
    get_security_baseline_payload,
    set_admin_auth_cookies,
)

router = APIRouter()


@router.get("/health")
async def health(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    admin_session: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
) -> dict:
    payload = {"status": "ok"}
    auth_mode = await resolve_admin_auth_mode(
        request,
        x_admin_token=x_admin_token,
        admin_session=admin_session,
    )
    if auth_mode is not None:
        payload["security"] = get_security_baseline_payload()
    return payload


@router.get("/auth/check", response_model=AuthStatusResponse)
@limiter.limit(RATE_LIMIT_ADMIN)
async def auth_check(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    admin_session: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
) -> AuthStatusResponse:
    auth_mode = await resolve_admin_auth_mode(
        request,
        x_admin_token=x_admin_token,
        x_csrf_token=x_csrf_token,
        admin_session=admin_session,
    )
    if auth_mode is None:
        raise _admin_auth_failure_exception()
    return AuthStatusResponse(ok=True, auth_mode=auth_mode)


@router.post("/auth/session", response_model=AuthStatusResponse)
@limiter.limit(RATE_LIMIT_ADMIN)
async def create_auth_session(
    request: Request,
    response: Response,
    payload: AuthSessionRequest,
) -> AuthStatusResponse:
    del request
    admin_token = get_admin_token()
    if admin_token:
        if not secrets.compare_digest(payload.password or "", admin_token):
            raise HTTPException(status_code=401, detail="Admin token required")
        await purge_expired_admin_sessions()
        session_token, csrf_token = generate_admin_session_tokens()
        await create_admin_session(
            session_token,
            csrf_token,
            expires_at=build_admin_session_expiry(get_admin_session_ttl_seconds()),
        )
        set_admin_auth_cookies(
            response,
            session_token=session_token,
            csrf_token=csrf_token,
        )
        return AuthStatusResponse(ok=True, auth_mode="session")
    if allow_unauthenticated_admin_in_dev():
        return AuthStatusResponse(ok=True, auth_mode="dev_override")
    raise _admin_auth_failure_exception()


@router.delete("/auth/session", response_model=AuthStatusResponse, dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_ADMIN)
async def delete_auth_session(
    request: Request,
    response: Response,
    admin_session: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
) -> AuthStatusResponse:
    del request
    if admin_session:
        await delete_admin_session(admin_session)
    clear_admin_auth_cookies(response)
    return AuthStatusResponse(ok=True, auth_mode="logged_out")
