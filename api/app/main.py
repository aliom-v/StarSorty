import os
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_settings
from .db import (
    count_unclassified_repos,
    get_repo,
    get_sync_status,
    init_db,
    list_repos,
    select_repos_for_classification,
    update_classification,
    update_override,
    update_readme_summary,
    update_sync_status,
    upsert_repos,
)
from .github import fetch_readme_summary, fetch_starred_repos_for_user, resolve_targets
from .ai_client import classify_repo_with_retry
from .taxonomy import load_taxonomy, validate_classification
from .rules import load_rules, match_rule
from .settings_store import write_settings

app = FastAPI(title="StarSorty API", version="0.1.0")
settings = get_settings()

origins: List[str] = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


class SyncResponse(BaseModel):
    status: str
    queued_at: str
    count: int


class StatusResponse(BaseModel):
    last_sync_at: str | None
    last_result: str | None
    last_message: str | None


class RepoOut(BaseModel):
    full_name: str
    name: str
    owner: str
    html_url: str
    description: str | None
    language: str | None
    stargazers_count: int | None
    forks_count: int | None
    topics: List[str]
    star_users: List[str]
    category: str | None
    subcategory: str | None
    tags: List[str]
    ai_category: str | None
    ai_subcategory: str | None
    ai_confidence: float | None
    ai_tags: List[str]
    ai_provider: str | None
    ai_model: str | None
    ai_updated_at: str | None
    override_category: str | None
    override_subcategory: str | None
    override_tags: List[str]
    override_note: str | None
    readme_summary: str | None
    readme_fetched_at: str | None
    pushed_at: str | None
    updated_at: str | None
    starred_at: str | None


class RepoListResponse(BaseModel):
    total: int
    items: List[RepoOut]


class OverrideRequest(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
    note: Optional[str] = None


class OverrideResponse(BaseModel):
    updated: bool


class ClassifyRequest(BaseModel):
    limit: int = 20
    force: bool = False
    include_readme: bool = True


class ClassifyResponse(BaseModel):
    total: int
    classified: int
    failed: int
    remaining_unclassified: int


class ReadmeResponse(BaseModel):
    updated: bool
    summary: str


class TaxonomyCategory(BaseModel):
    name: str
    subcategories: List[str] = []


class TaxonomyResponse(BaseModel):
    categories: List[TaxonomyCategory]
    tags: List[str]


class SettingsResponse(BaseModel):
    github_username: str
    github_target_username: str
    github_usernames: str
    github_include_self: bool
    github_mode: str
    ai_provider: str
    ai_model: str
    ai_base_url: str
    ai_headers_json: str
    ai_temperature: float
    ai_max_tokens: int
    ai_timeout: int
    ai_taxonomy_path: str
    rules_json: str
    sync_cron: str
    sync_timeout: int
    github_token_set: bool
    ai_api_key_set: bool


class SettingsRequest(BaseModel):
    github_username: Optional[str] = None
    github_target_username: Optional[str] = None
    github_usernames: Optional[str] = None
    github_include_self: Optional[bool] = None
    github_mode: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_headers_json: Optional[str] = None
    ai_temperature: Optional[float] = None
    ai_max_tokens: Optional[int] = None
    ai_timeout: Optional[int] = None
    ai_taxonomy_path: Optional[str] = None
    rules_json: Optional[str] = None
    sync_cron: Optional[str] = None
    sync_timeout: Optional[int] = None


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    status_data = get_sync_status()
    return StatusResponse(**status_data)


@app.post("/sync", response_model=SyncResponse)
def sync() -> SyncResponse:
    try:
        targets = resolve_targets()
    except Exception as exc:
        timestamp = update_sync_status("error", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total = 0
    for username, use_auth in targets:
        try:
            repos = fetch_starred_repos_for_user(username, use_auth)
        except Exception as exc:
            timestamp = update_sync_status("error", str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        for repo in repos:
            repo["star_users"] = [username]
        total += upsert_repos(repos)

    timestamp = update_sync_status("ok", f"synced {total} repos")
    return SyncResponse(status="ok", queued_at=timestamp, count=total)


@app.get("/repos", response_model=RepoListResponse)
def repos(
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    star_user: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> RepoListResponse:
    total, items = list_repos(
        q=q,
        language=language,
        min_stars=min_stars,
        category=category,
        tag=tag,
        star_user=star_user,
        limit=limit,
        offset=offset,
    )
    return RepoListResponse(total=total, items=items)


@app.get("/repos/{full_name:path}", response_model=RepoOut)
def repo_detail(full_name: str) -> RepoOut:
    repo = get_repo(full_name)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    return RepoOut(**repo)


@app.patch("/repos/{full_name:path}/override", response_model=OverrideResponse)
def repo_override(full_name: str, payload: OverrideRequest) -> OverrideResponse:
    fields = payload.model_fields_set
    updates: Dict[str, Optional[object]] = {}
    if "category" in fields:
        updates["category"] = payload.category
    if "subcategory" in fields:
        updates["subcategory"] = payload.subcategory
    if "tags" in fields:
        updates["tags"] = payload.tags
    if "note" in fields:
        updates["note"] = payload.note

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    updated = update_override(full_name, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Repo not found or no updates")
    return OverrideResponse(updated=True)


@app.post("/repos/{full_name:path}/readme", response_model=ReadmeResponse)
def repo_readme(full_name: str) -> ReadmeResponse:
    if not get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    summary = fetch_readme_summary(full_name)
    if summary:
        update_readme_summary(full_name, summary)
    return ReadmeResponse(updated=bool(summary), summary=summary)


@app.get("/taxonomy", response_model=TaxonomyResponse)
def taxonomy() -> TaxonomyResponse:
    current = get_settings()
    data = load_taxonomy(current.ai_taxonomy_path)
    return TaxonomyResponse(categories=data.get("categories", []), tags=data.get("tags", []))


@app.post("/classify", response_model=ClassifyResponse)
def classify(payload: ClassifyRequest) -> ClassifyResponse:
    current = get_settings()
    try:
        data = load_taxonomy(current.ai_taxonomy_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repos_to_classify = select_repos_for_classification(payload.limit, payload.force)
    rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
    rules = load_rules(current.rules_json, fallback_path=rules_path)
    use_ai = current.ai_provider.lower() not in ("", "none")
    if not use_ai and not rules:
        raise HTTPException(status_code=400, detail="AI_PROVIDER or RULES_JSON is required")

    classified = 0
    failed = 0
    for repo in repos_to_classify:
        repo_data = dict(repo)
        if payload.include_readme:
            description = (repo_data.get("description") or "").strip()
            if len(description) < 20 and not repo_data.get("readme_summary"):
                try:
                    summary = fetch_readme_summary(repo_data["full_name"])
                except Exception:
                    summary = ""
                if summary:
                    update_readme_summary(repo_data["full_name"], summary)
                    repo_data["readme_summary"] = summary
        rule = match_rule(repo_data, rules)
        if rule:
            validated = validate_classification(
                {
                    "category": rule.get("category"),
                    "subcategory": rule.get("subcategory"),
                    "tags": rule.get("tags") or [],
                    "confidence": 1.0,
                },
                data,
            )
            update_classification(
                repo_data["full_name"],
                validated["category"],
                validated["subcategory"],
                validated["confidence"],
                validated["tags"],
                "rules",
                "rules",
            )
            classified += 1
            continue
        if not use_ai:
            failed += 1
            continue
        try:
            result = classify_repo_with_retry(repo_data, data, retries=2)
            update_classification(
                repo_data["full_name"],
                result["category"],
                result["subcategory"],
                result["confidence"],
                result["tags"],
                result["provider"],
                result["model"],
            )
            classified += 1
        except Exception:
            failed += 1

    return ClassifyResponse(
        total=len(repos_to_classify),
        classified=classified,
        failed=failed,
        remaining_unclassified=count_unclassified_repos(),
    )


@app.get("/settings", response_model=SettingsResponse)
def settings() -> SettingsResponse:
    current = get_settings()
    return SettingsResponse(
        github_username=current.github_username,
        github_target_username=current.github_target_username,
        github_usernames=current.github_usernames,
        github_include_self=current.github_include_self,
        github_mode=current.github_mode,
        ai_provider=current.ai_provider,
        ai_model=current.ai_model,
        ai_base_url=current.ai_base_url,
        ai_headers_json=current.ai_headers_json,
        ai_temperature=current.ai_temperature,
        ai_max_tokens=current.ai_max_tokens,
        ai_timeout=current.ai_timeout,
        ai_taxonomy_path=current.ai_taxonomy_path,
        rules_json=current.rules_json,
        sync_cron=current.sync_cron,
        sync_timeout=current.sync_timeout,
        github_token_set=bool(os.getenv("GITHUB_TOKEN")),
        ai_api_key_set=bool(os.getenv("AI_API_KEY")),
    )


@app.patch("/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsRequest) -> SettingsResponse:
    fields = payload.model_fields_set
    updates: Dict[str, Optional[object]] = {}

    for field in fields:
        updates[field.upper()] = getattr(payload, field)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    write_settings(updates)
    current = get_settings()
    return SettingsResponse(
        github_username=current.github_username,
        github_target_username=current.github_target_username,
        github_usernames=current.github_usernames,
        github_include_self=current.github_include_self,
        github_mode=current.github_mode,
        ai_provider=current.ai_provider,
        ai_model=current.ai_model,
        ai_base_url=current.ai_base_url,
        ai_headers_json=current.ai_headers_json,
        ai_temperature=current.ai_temperature,
        ai_max_tokens=current.ai_max_tokens,
        ai_timeout=current.ai_timeout,
        ai_taxonomy_path=current.ai_taxonomy_path,
        rules_json=current.rules_json,
        sync_cron=current.sync_cron,
        sync_timeout=current.sync_timeout,
        github_token_set=bool(os.getenv("GITHUB_TOKEN")),
        ai_api_key_set=bool(os.getenv("AI_API_KEY")),
    )
