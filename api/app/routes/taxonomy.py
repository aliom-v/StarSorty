from fastapi import APIRouter

from ..config import get_settings
from ..schemas import TaxonomyResponse
from ..taxonomy import load_taxonomy

router = APIRouter()


@router.get("/taxonomy", response_model=TaxonomyResponse)
async def taxonomy() -> TaxonomyResponse:
    current = get_settings()
    data = load_taxonomy(current.ai_taxonomy_path)
    return TaxonomyResponse(
        categories=data.get("categories", []),
        tags=data.get("tags", []),
        tag_defs=data.get("tag_defs", []),
    )
