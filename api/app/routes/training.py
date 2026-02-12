from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from ..db import get_repo, list_training_samples
from ..deps import _normalized_optional, require_admin
from ..models import RepoBase
from ..schemas import (
    FewShotItem,
    FewShotResponse,
    TrainingSampleItem,
    TrainingSamplesResponse,
)

router = APIRouter()


@router.get(
    "/training/samples",
    response_model=TrainingSamplesResponse,
    dependencies=[Depends(require_admin)],
)
async def training_samples(
    user_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> TrainingSamplesResponse:
    items = await list_training_samples(_normalized_optional(user_id), limit=limit)
    return TrainingSamplesResponse(items=[TrainingSampleItem(**item) for item in items], total=len(items))


@router.get(
    "/training/fewshot",
    response_model=FewShotResponse,
    dependencies=[Depends(require_admin)],
)
async def training_fewshot(
    user_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> FewShotResponse:
    samples = await list_training_samples(_normalized_optional(user_id), limit=limit)
    items: List[FewShotItem] = []
    for sample in samples:
        repo = await get_repo(sample["full_name"])
        if not repo:
            continue
        repo_payload = repo.model_dump() if isinstance(repo, RepoBase) else dict(repo)
        items.append(
            FewShotItem(
                input={
                    "full_name": repo_payload.get("full_name"),
                    "name": repo_payload.get("name"),
                    "description": repo_payload.get("description"),
                    "topics": repo_payload.get("topics") or [],
                    "readme_summary": repo_payload.get("readme_summary"),
                },
                output={
                    "category": sample.get("after_category"),
                    "subcategory": sample.get("after_subcategory"),
                    "tag_ids": sample.get("after_tag_ids") or [],
                },
                note=sample.get("note"),
            )
        )
    return FewShotResponse(items=items, total=len(items))
