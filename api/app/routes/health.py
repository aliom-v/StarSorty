from fastapi import APIRouter, Depends, Header, Request

from ..deps import require_admin
from ..rate_limit import limiter, RATE_LIMIT_ADMIN
from ..security import get_security_baseline_payload, is_admin_token_valid

router = APIRouter()


@router.get("/health")
async def health(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> dict:
    payload = {"status": "ok"}
    if is_admin_token_valid(x_admin_token):
        payload["security"] = get_security_baseline_payload()
    return payload


@router.get("/auth/check", dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_ADMIN)
async def auth_check(request: Request) -> dict:
    return {"ok": True}
