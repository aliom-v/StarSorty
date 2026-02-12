from fastapi import APIRouter, Depends, Request

from ..db import (
    get_user_interest_profile,
    get_user_preferences,
    record_user_feedback_event,
    update_user_preferences,
)
from ..deps import _normalize_preference_user, require_admin
from ..rate_limit import limiter, RATE_LIMIT_DEFAULT
from ..schemas import (
    ClickFeedbackRequest,
    FeedbackResponse,
    InterestProfileResponse,
    SearchFeedbackRequest,
    UserPreferencesRequest,
    UserPreferencesResponse,
)

router = APIRouter()


@router.get("/preferences/{user_id}", response_model=UserPreferencesResponse)
async def get_preferences(user_id: str) -> UserPreferencesResponse:
    preference = await get_user_preferences(_normalize_preference_user(user_id))
    return UserPreferencesResponse(**preference)


@router.patch(
    "/preferences/{user_id}",
    response_model=UserPreferencesResponse,
    dependencies=[Depends(require_admin)],
)
async def patch_preferences(user_id: str, payload: UserPreferencesRequest) -> UserPreferencesResponse:
    updated = await update_user_preferences(
        _normalize_preference_user(user_id),
        tag_mapping=payload.tag_mapping,
        rule_priority=payload.rule_priority,
    )
    return UserPreferencesResponse(**updated)


@router.post("/feedback/search", response_model=FeedbackResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def feedback_search(request: Request, payload: SearchFeedbackRequest) -> FeedbackResponse:
    await record_user_feedback_event(
        user_id=_normalize_preference_user(payload.user_id),
        event_type="search",
        query=payload.query,
        payload={
            "query": payload.query,
            "results_count": payload.results_count,
            "tags": payload.selected_tags,
            "category": payload.category,
            "subcategory": payload.subcategory,
        },
    )
    return FeedbackResponse(ok=True)


@router.post("/feedback/click", response_model=FeedbackResponse)
@limiter.limit(RATE_LIMIT_DEFAULT)
async def feedback_click(request: Request, payload: ClickFeedbackRequest) -> FeedbackResponse:
    await record_user_feedback_event(
        user_id=_normalize_preference_user(payload.user_id),
        event_type="click",
        query=payload.query,
        full_name=payload.full_name,
        payload={"query": payload.query},
    )
    return FeedbackResponse(ok=True)


@router.get("/interest/{user_id}", response_model=InterestProfileResponse)
async def interest_profile(user_id: str) -> InterestProfileResponse:
    profile = await get_user_interest_profile(_normalize_preference_user(user_id))
    return InterestProfileResponse(**profile)
