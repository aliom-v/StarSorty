from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..db import iter_repos_for_export
from ..deps import require_admin
from ..export import generate_obsidian_zip_streaming
from ..rate_limit import limiter, RATE_LIMIT_HEAVY

router = APIRouter()


@router.get("/export/obsidian", dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_HEAVY)
async def export_obsidian(
    request: Request,
    tags: Optional[str] = None,
    language: Optional[str] = None,
) -> StreamingResponse:
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    repo_iter = iter_repos_for_export(language=language, tags=tag_list)
    return StreamingResponse(
        generate_obsidian_zip_streaming(repo_iter),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="starsorty-export.zip"'},
    )
