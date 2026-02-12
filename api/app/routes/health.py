from fastapi import APIRouter, Depends, Request

from ..deps import require_admin
from ..rate_limit import limiter, RATE_LIMIT_ADMIN

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/auth/check", dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_ADMIN)
async def auth_check(request: Request) -> dict:
    return {"ok": True}
