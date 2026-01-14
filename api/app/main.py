import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_settings
from .db import (
    count_unclassified_repos,
    count_repos_for_classification,
    get_repo_stats,
    get_repo,
    get_sync_status,
    init_db,
    list_override_history,
    list_repos,
    prune_star_user,
    prune_users_not_in,
    record_readme_fetch,
    select_repos_for_classification,
    update_classification,
    update_override,
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
DEFAULT_CLASSIFY_BATCH_SIZE = int(os.getenv("CLASSIFY_BATCH_SIZE", "50"))
DEFAULT_CLASSIFY_CONCURRENCY = int(os.getenv("CLASSIFY_CONCURRENCY", "3"))
CLASSIFY_CONCURRENCY_MAX = int(os.getenv("CLASSIFY_CONCURRENCY_MAX", "10"))
CLASSIFY_BATCH_DELAY_MS = int(os.getenv("CLASSIFY_BATCH_DELAY_MS", "0"))

origins: List[str] = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

classification_lock = Lock()
classification_stop = Event()
classification_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "failed": 0,
    "remaining": 0,
    "last_error": None,
    "batch_size": 0,
    "concurrency": 0,
}


def require_admin(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")) -> None:
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    if not admin_token:
        return
    if x_admin_token != admin_token:
        raise HTTPException(status_code=401, detail="Admin token required")


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


class OverrideHistoryItem(BaseModel):
    category: str | None
    subcategory: str | None
    tags: List[str]
    note: str | None
    updated_at: str | None


class OverrideHistoryResponse(BaseModel):
    items: List[OverrideHistoryItem]


class ClassifyRequest(BaseModel):
    limit: int = 20
    force: bool = False
    include_readme: bool = True


class ClassifyResponse(BaseModel):
    total: int
    classified: int
    failed: int
    remaining_unclassified: int


class BackgroundClassifyRequest(ClassifyRequest):
    concurrency: Optional[int] = None


class BackgroundClassifyResponse(BaseModel):
    started: bool
    running: bool
    message: str


class BackgroundClassifyStatusResponse(BaseModel):
    running: bool
    started_at: str | None
    finished_at: str | None
    processed: int
    failed: int
    remaining: int
    last_error: str | None
    batch_size: int
    concurrency: int


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


class StatsItem(BaseModel):
    name: str
    count: int


class StatsResponse(BaseModel):
    total: int
    unclassified: int
    categories: List[StatsItem]
    tags: List[StatsItem]
    users: List[StatsItem]


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


@app.post("/sync", response_model=SyncResponse, dependencies=[Depends(require_admin)])
def sync() -> SyncResponse:
    try:
        targets = resolve_targets()
    except Exception as exc:
        timestamp = update_sync_status("error", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total = 0
    removed_total = 0
    deleted_total = 0
    for username, use_auth in targets:
        try:
            repos = fetch_starred_repos_for_user(username, use_auth)
        except Exception as exc:
            timestamp = update_sync_status("error", str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        for repo in repos:
            repo["star_users"] = [username]
        total += upsert_repos(repos)
        keep_names = [repo.get("full_name") for repo in repos if repo.get("full_name")]
        removed, deleted = prune_star_user(username, keep_names)
        removed_total += removed
        deleted_total += deleted

    allowed_users = [name for name, _ in targets]
    cleaned_total, cleaned_deleted = prune_users_not_in(allowed_users)

    timestamp = update_sync_status(
        "ok",
        (
            f"synced {total} repos, pruned {removed_total} stars, removed {deleted_total} repos, "
            f"cleaned {cleaned_total} repos, removed {cleaned_deleted} repos"
        ),
    )
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


@app.patch(
    "/repos/{full_name:path}/override",
    response_model=OverrideResponse,
    dependencies=[Depends(require_admin)],
)
def repo_override(full_name: str, payload: OverrideRequest) -> OverrideResponse:
    fields = payload.model_fields_set
    updates: Dict[str, Optional[object]] = {}
    if "category" in fields:
        if payload.category is not None and not str(payload.category).strip():
            raise HTTPException(status_code=400, detail="category cannot be empty")
        updates["category"] = payload.category
    if "subcategory" in fields:
        if payload.subcategory is not None and not str(payload.subcategory).strip():
            raise HTTPException(status_code=400, detail="subcategory cannot be empty")
        updates["subcategory"] = payload.subcategory
    if "tags" in fields:
        tags = payload.tags or []
        updates["tags"] = [tag for tag in tags if str(tag).strip()]
    if "note" in fields:
        if payload.note is not None and not str(payload.note).strip():
            raise HTTPException(status_code=400, detail="note cannot be empty")
        updates["note"] = payload.note

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")

    updated = update_override(full_name, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Repo not found or no updates")
    return OverrideResponse(updated=True)


@app.get("/repos/{full_name:path}/overrides", response_model=OverrideHistoryResponse)
def repo_override_history(full_name: str) -> OverrideHistoryResponse:
    if not get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    items = list_override_history(full_name)
    return OverrideHistoryResponse(items=items)


@app.post(
    "/repos/{full_name:path}/readme",
    response_model=ReadmeResponse,
    dependencies=[Depends(require_admin)],
)
def repo_readme(full_name: str) -> ReadmeResponse:
    if not get_repo(full_name):
        raise HTTPException(status_code=404, detail="Repo not found")
    try:
        summary = fetch_readme_summary(full_name)
    except Exception as exc:
        record_readme_fetch(full_name, None, False)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    record_readme_fetch(full_name, summary, True)
    return ReadmeResponse(updated=bool(summary), summary=summary)


@app.get("/taxonomy", response_model=TaxonomyResponse)
def taxonomy() -> TaxonomyResponse:
    current = get_settings()
    data = load_taxonomy(current.ai_taxonomy_path)
    return TaxonomyResponse(categories=data.get("categories", []), tags=data.get("tags", []))


def _update_classification_state(**updates: object) -> None:
    with classification_lock:
        classification_state.update(updates)


def _get_classification_state() -> dict:
    with classification_lock:
        return dict(classification_state)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _should_fetch_readme(repo_data: dict) -> bool:
    description = (repo_data.get("description") or "").strip()
    if len(description) >= 20:
        return False
    if repo_data.get("readme_summary"):
        return False
    failures = int(repo_data.get("readme_failures") or 0)
    if failures >= 3:
        return False
    last_attempt = _parse_timestamp(repo_data.get("readme_last_attempt_at"))
    if last_attempt:
        now = datetime.now(timezone.utc)
        if now - last_attempt < timedelta(minutes=1):
            return False
    return True


def _classify_repo_once(
    repo: dict,
    data: dict,
    rules: list,
    use_ai: bool,
    include_readme: bool,
) -> bool:
    repo_data = dict(repo)
    if include_readme:
        if _should_fetch_readme(repo_data):
            try:
                summary = fetch_readme_summary(repo_data["full_name"])
                record_readme_fetch(repo_data["full_name"], summary, True)
            except Exception:
                record_readme_fetch(repo_data["full_name"], None, False)
                summary = ""
            if summary:
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
        return True
    if not use_ai:
        return False
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
    return True


def _classify_repos_concurrent(
    repos_to_classify: list,
    data: dict,
    rules: list,
    use_ai: bool,
    include_readme: bool,
    concurrency: int,
) -> tuple[int, int]:
    if concurrency <= 1 or len(repos_to_classify) <= 1:
        classified = 0
        failed = 0
        for repo in repos_to_classify:
            try:
                if _classify_repo_once(repo, data, rules, use_ai, include_readme):
                    classified += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        return (classified, failed)

    classified = 0
    failed = 0

    def classify_single(repo: dict) -> tuple[int, int]:
        try:
            return (1, 0) if _classify_repo_once(repo, data, rules, use_ai, include_readme) else (0, 1)
        except Exception:
            return (0, 1)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(classify_single, repo) for repo in repos_to_classify]
        for future in as_completed(futures):
            item_classified, item_failed = future.result()
            classified += item_classified
            failed += item_failed
    return (classified, failed)


def _clamp_concurrency(value: int) -> int:
    if value < 1:
        return 1
    if value > CLASSIFY_CONCURRENCY_MAX:
        return CLASSIFY_CONCURRENCY_MAX
    return value


def _background_classify_loop(payload: BackgroundClassifyRequest) -> None:
    try:
        current = get_settings()
        data = load_taxonomy(current.ai_taxonomy_path)
        rules_path = Path(__file__).resolve().parents[1] / "config" / "rules.json"
        rules = load_rules(current.rules_json, fallback_path=rules_path)
        use_ai = current.ai_provider.lower() not in ("", "none")
        if not use_ai and not rules:
            raise ValueError("AI_PROVIDER or RULES_JSON is required")

        batch_size = payload.limit if payload.limit and payload.limit > 0 else DEFAULT_CLASSIFY_BATCH_SIZE
        concurrency_value = payload.concurrency if payload.concurrency and payload.concurrency > 0 else DEFAULT_CLASSIFY_CONCURRENCY
        concurrency = _clamp_concurrency(concurrency_value)
        force_mode = bool(payload.force)
        snapshot_repos = None
        if force_mode:
            snapshot_repos = select_repos_for_classification(0, True)
            remaining = len(snapshot_repos)
        else:
            remaining = count_repos_for_classification(False)

        _update_classification_state(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            processed=0,
            failed=0,
            remaining=remaining,
            last_error=None,
            batch_size=batch_size,
            concurrency=concurrency,
        )

        previous_remaining = None
        snapshot_index = 0
        while not classification_stop.is_set():
            if force_mode:
                if not snapshot_repos:
                    break
                repos_to_classify = snapshot_repos[snapshot_index : snapshot_index + batch_size]
                snapshot_index += len(repos_to_classify)
            else:
                repos_to_classify = select_repos_for_classification(batch_size, False)
            if not repos_to_classify:
                break

            batch_classified, batch_failed = _classify_repos_concurrent(
                repos_to_classify,
                data,
                rules,
                use_ai,
                payload.include_readme,
                concurrency,
            )
            processed = batch_classified + batch_failed
            if force_mode:
                remaining = max(0, (len(snapshot_repos or []) - snapshot_index))
            else:
                remaining = count_repos_for_classification(False)
            state = _get_classification_state()
            _update_classification_state(
                processed=state["processed"] + processed,
                failed=state["failed"] + batch_failed,
                remaining=remaining,
            )

            if processed == 0:
                break
            if not force_mode and previous_remaining is not None and remaining >= previous_remaining:
                break
            previous_remaining = remaining
            if CLASSIFY_BATCH_DELAY_MS > 0:
                time.sleep(CLASSIFY_BATCH_DELAY_MS / 1000)

        _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            last_error=str(exc),
        )


@app.post("/classify", response_model=ClassifyResponse, dependencies=[Depends(require_admin)])
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

    classified, failed = _classify_repos_concurrent(
        repos_to_classify,
        data,
        rules,
        use_ai,
        payload.include_readme,
        concurrency=1,
    )

    return ClassifyResponse(
        total=len(repos_to_classify),
        classified=classified,
        failed=failed,
        remaining_unclassified=count_unclassified_repos(),
    )


@app.post(
    "/classify/background",
    response_model=BackgroundClassifyResponse,
    dependencies=[Depends(require_admin)],
)
def classify_background(payload: BackgroundClassifyRequest) -> BackgroundClassifyResponse:
    with classification_lock:
        if classification_state["running"]:
            return BackgroundClassifyResponse(
                started=False, running=True, message="Classification already running"
            )
        classification_stop.clear()
        classification_state["running"] = True
        thread = Thread(target=_background_classify_loop, args=(payload,), daemon=True)
        thread.start()

    return BackgroundClassifyResponse(
        started=True, running=True, message="Background classification started"
    )


@app.get("/classify/status", response_model=BackgroundClassifyStatusResponse)
def classify_status() -> BackgroundClassifyStatusResponse:
    state = _get_classification_state()
    return BackgroundClassifyStatusResponse(**state)


@app.post("/classify/stop", dependencies=[Depends(require_admin)])
def classify_stop() -> dict:
    classification_stop.set()
    _update_classification_state(last_error="Stopped by user")
    return {"stopped": True}


@app.get("/stats", response_model=StatsResponse)
def stats() -> StatsResponse:
    data = get_repo_stats()
    return StatsResponse(**data)


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


@app.patch("/settings", response_model=SettingsResponse, dependencies=[Depends(require_admin)])
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
