import asyncio
import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..deps import require_admin
from ..rules import load_rules
from ..schemas import (
    ClientSettingsResponse,
    SettingsRequest,
    SettingsResponse,
)
from ..settings_store import write_settings

router = APIRouter()


def _resolve_classify_context_for_validation(current, rules: list) -> None:
    from .classify import _resolve_classify_context
    _resolve_classify_context(current, rules, allow_fallback=False)


@router.get("/api/config/client-settings", response_model=ClientSettingsResponse)
async def client_settings() -> ClientSettingsResponse:
    current = get_settings()
    rules_path = Path(__file__).resolve().parents[2] / "config" / "rules.json"
    rules = load_rules(current.rules_json, fallback_path=rules_path)
    try:
        _resolve_classify_context_for_validation(current, rules)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Server configuration error: {exc}. Check server .env settings.",
        ) from exc
    return ClientSettingsResponse(
        github_mode=current.github_mode,
        classify_mode=current.classify_mode,
        auto_classify_after_sync=current.auto_classify_after_sync,
    )


@router.get("/settings", response_model=SettingsResponse)
async def settings() -> SettingsResponse:
    current = get_settings()
    return SettingsResponse(
        github_username=current.github_username,
        github_target_username=current.github_target_username,
        github_usernames=current.github_usernames,
        github_include_self=current.github_include_self,
        github_mode=current.github_mode,
        classify_mode=current.classify_mode,
        auto_classify_after_sync=current.auto_classify_after_sync,
        rules_json=current.rules_json,
        sync_cron=current.sync_cron,
        sync_timeout=current.sync_timeout,
        github_token_set=bool(os.getenv("GITHUB_TOKEN")),
        ai_api_key_set=bool(os.getenv("AI_API_KEY")),
    )


@router.patch("/settings", response_model=SettingsResponse, dependencies=[Depends(require_admin)])
async def update_settings(payload: SettingsRequest) -> SettingsResponse:
    fields = payload.model_fields_set
    updates: Dict[str, Optional[object]] = {}

    for field in fields:
        updates[field.upper()] = getattr(payload, field)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    await asyncio.to_thread(write_settings, updates)
    current = get_settings()
    return SettingsResponse(
        github_username=current.github_username,
        github_target_username=current.github_target_username,
        github_usernames=current.github_usernames,
        github_include_self=current.github_include_self,
        github_mode=current.github_mode,
        classify_mode=current.classify_mode,
        auto_classify_after_sync=current.auto_classify_after_sync,
        rules_json=current.rules_json,
        sync_cron=current.sync_cron,
        sync_timeout=current.sync_timeout,
        github_token_set=bool(os.getenv("GITHUB_TOKEN")),
        ai_api_key_set=bool(os.getenv("AI_API_KEY")),
    )
