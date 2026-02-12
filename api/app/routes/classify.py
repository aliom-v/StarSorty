import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..ai_client import AIClient
from ..cache import cache
from ..classification.decision import DecisionPolicy
from ..classification.engine import ClassificationEngine
from ..config import get_settings
from ..db import (
    count_repos_for_classification,
    count_unclassified_repos,
    get_user_preferences,
    increment_classify_fail_count,
    record_readme_fetch,
    record_readme_fetches,
    select_repos_for_classification,
    update_classification,
    update_classifications_bulk,
)
from ..deps import (
    _normalize_preference_user,
    _now_iso,
    _register_task,
    _set_task_status,
    require_admin,
)
from ..github import GitHubClient
from ..models import RepoBase
from ..rate_limit import limiter, RATE_LIMIT_HEAVY
from ..rules import load_rules
from ..schemas import (
    BackgroundClassifyRequest,
    BackgroundClassifyResponse,
    BackgroundClassifyStatusResponse,
    ClassifyRequest,
    ClassifyResponse,
    TaskQueuedResponse,
)
from ..state import (
    AI_CLASSIFY_BATCH_SIZE,
    CLASSIFY_BATCH_DELAY_MS,
    CLASSIFY_BATCH_SIZE_MAX,
    CLASSIFY_CONCURRENCY_MAX,
    CLASSIFY_ENGINE_V2_ENABLED,
    CLASSIFY_REMAINING_REFRESH_EVERY,
    DEFAULT_CLASSIFY_BATCH_SIZE,
    DEFAULT_CLASSIFY_CONCURRENCY,
    RULE_AI_THRESHOLD,
    RULE_DIRECT_THRESHOLD,
    _add_quality_metrics,
    _get_classification_state,
    _update_classification_state,
    classification_lock,
    classification_state,
    classification_stop,
    classification_task,
)
from ..taxonomy import load_taxonomy, normalize_tags_to_ids

logger = logging.getLogger("starsorty.api")

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers (classify context, preference, tag mapping)
# ---------------------------------------------------------------------------

def _normalize_provider(value: str) -> str:
    return str(value or "").strip().lower()


def _validate_ai_settings(current) -> tuple[bool, str]:
    provider = _normalize_provider(current.ai_provider)
    if provider in ("", "none"):
        return False, "AI_PROVIDER is not configured"
    if not str(current.ai_model or "").strip():
        return False, "AI_MODEL is required for AI classification"
    if provider in ("openai", "anthropic") and not str(current.ai_api_key or "").strip():
        return False, f"AI_API_KEY is required for provider {provider}"
    if provider not in ("openai", "anthropic") and not str(current.ai_base_url or "").strip():
        return False, f"AI_BASE_URL is required for provider {provider or 'custom'}"
    return True, ""


def _resolve_classify_context(
    current,
    rules: list,
    allow_fallback: bool,
) -> tuple[str, bool, str | None]:
    classify_mode = current.classify_mode
    rules_available = bool(rules)
    ai_ok, ai_reason = _validate_ai_settings(current)

    if classify_mode == "ai_only":
        if ai_ok:
            return classify_mode, True, None
        if allow_fallback and rules_available:
            return "rules_only", False, f"{ai_reason}. Falling back to rules_only."
        if allow_fallback:
            return classify_mode, False, f"{ai_reason}. Skipping classification."
        raise ValueError(ai_reason)

    if classify_mode == "rules_only":
        if rules_available:
            return classify_mode, False, None
        if allow_fallback and ai_ok:
            return "ai_only", True, "RULES_JSON is required for classify_mode=rules_only. Falling back to ai_only."
        if allow_fallback:
            return classify_mode, False, "RULES_JSON is required for classify_mode=rules_only."
        raise ValueError("RULES_JSON is required for classify_mode=rules_only")

    if rules_available or ai_ok:
        if not ai_ok and rules_available and allow_fallback:
            return "rules_only", False, f"{ai_reason}. Falling back to rules_only."
        return classify_mode, ai_ok, None

    if allow_fallback:
        return classify_mode, False, "AI_PROVIDER or RULES_JSON is required"
    raise ValueError("AI_PROVIDER or RULES_JSON is required")


def _apply_rule_priority_overrides(
    rules: List[Dict[str, object]],
    preference: Dict[str, object],
) -> List[Dict[str, object]]:
    priority_map_raw = preference.get("rule_priority") if isinstance(preference, dict) else {}
    if not isinstance(priority_map_raw, dict) or not priority_map_raw:
        return list(rules)
    adjusted: List[Dict[str, object]] = []
    for rule in rules:
        copied = dict(rule)
        rule_id = str(copied.get("rule_id") or "").strip()
        delta = priority_map_raw.get(rule_id)
        if delta is not None:
            try:
                copied["priority"] = int(copied.get("priority", 0)) + int(delta)
            except (TypeError, ValueError):
                pass
        adjusted.append(copied)
    return adjusted


def _resolve_tag_mapping(
    taxonomy: dict,
    preference: Dict[str, object],
) -> Dict[str, str]:
    mapping_raw = preference.get("tag_mapping") if isinstance(preference, dict) else {}
    if not isinstance(mapping_raw, dict):
        return {}
    tag_mapping: Dict[str, str] = {}
    for source, target in mapping_raw.items():
        source_ids = normalize_tags_to_ids([str(source)], taxonomy)
        target_ids = normalize_tags_to_ids([str(target)], taxonomy)
        if not source_ids or not target_ids:
            continue
        tag_mapping[source_ids[0]] = target_ids[0]
    return tag_mapping


def _apply_tag_mapping_to_result(result: Dict[str, object], mapping: Dict[str, str], taxonomy: dict) -> Dict[str, object]:
    if not mapping:
        return result
    tag_ids = [str(v) for v in (result.get("tag_ids") or []) if str(v).strip()]
    if not tag_ids:
        tag_ids = normalize_tags_to_ids([str(v) for v in (result.get("tags") or [])], taxonomy)
    remapped: List[str] = []
    seen: set[str] = set()
    for tag_id in tag_ids:
        mapped = mapping.get(tag_id, tag_id)
        if mapped in seen:
            continue
        seen.add(mapped)
        remapped.append(mapped)
    tag_id_to_name = taxonomy.get("tag_id_to_name") or {}
    mapped_tags = [tag_id_to_name.get(tag_id, tag_id) for tag_id in remapped]
    updated = dict(result)
    updated["tag_ids"] = remapped
    updated["tags"] = mapped_tags
    return updated


# ---------------------------------------------------------------------------
# Clamping helpers
# ---------------------------------------------------------------------------

def _clamp_concurrency(value: int) -> int:
    if value < 1:
        return 1
    if value > CLASSIFY_CONCURRENCY_MAX:
        return CLASSIFY_CONCURRENCY_MAX
    return value


def _clamp_batch_size(value: int) -> int:
    if value < 1:
        return 1
    if value > CLASSIFY_BATCH_SIZE_MAX:
        return CLASSIFY_BATCH_SIZE_MAX
    return value


# ---------------------------------------------------------------------------
# README helper
# ---------------------------------------------------------------------------

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
    if repo_data.get("readme_empty"):
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


def _chunk_repos(items: list, size: int) -> list[list]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


# ---------------------------------------------------------------------------
# Classification core logic
# ---------------------------------------------------------------------------

async def _classify_repo_once(
    repo: dict,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    include_readme: bool,
    github_client: GitHubClient,
    ai_client: AIClient,
) -> bool:
    if isinstance(repo, RepoBase):
        repo_data = repo.model_dump()
    else:
        repo_data = dict(repo)
    if include_readme:
        if _should_fetch_readme(repo_data):
            summary = ""
            try:
                summary = await github_client.fetch_readme_summary(repo_data["full_name"])
            except Exception:
                try:
                    await record_readme_fetch(repo_data["full_name"], None, False)
                except Exception:
                    logger.warning(
                        "Failed to record README fetch failure for %s",
                        repo_data.get("full_name"),
                    )
            else:
                try:
                    await record_readme_fetch(repo_data["full_name"], summary, True)
                except Exception as exc:
                    logger.warning(
                        "Failed to persist README summary for %s: %s",
                        repo_data.get("full_name"),
                        exc,
                    )
            if summary:
                repo_data["readme_summary"] = summary
    if CLASSIFY_ENGINE_V2_ENABLED:
        policy = DecisionPolicy(
            direct_rule_threshold=RULE_DIRECT_THRESHOLD,
            ai_required_threshold=RULE_AI_THRESHOLD,
        )
    else:
        policy = DecisionPolicy(direct_rule_threshold=0.0, ai_required_threshold=1.0)
    engine = ClassificationEngine(
        taxonomy=data,
        rules=rules,
        classify_mode=classify_mode,
        use_ai=use_ai,
        policy=policy,
    )
    outcome = await engine.classify_repo(repo_data, ai_client, ai_retries=2)
    result = outcome.result
    provider = result.get("provider") if outcome.source == "ai" else "rules"
    model = result.get("model") if outcome.source == "ai" else "rules"
    if outcome.source == "manual_review":
        provider = "manual"
        model = "manual"
    rule_candidates = [
        {
            "rule_id": candidate.rule_id,
            "score": candidate.score,
            "category": candidate.category,
            "subcategory": candidate.subcategory,
            "evidence": candidate.evidence,
            "tag_ids": candidate.tag_ids,
        }
        for candidate in outcome.rule_candidates[:5]
    ]
    await update_classification(
        repo_data["full_name"],
        result["category"],
        result["subcategory"],
        result["confidence"],
        result["tags"],
        result.get("tag_ids"),
        provider,
        model,
        summary_zh=result.get("summary_zh"),
        keywords=result.get("keywords"),
        reason=str(result.get("reason") or outcome.reason or "")[:500],
        decision_source=outcome.source,
        rule_candidates=rule_candidates,
    )
    return True


async def _classify_repos_batch(
    repos: list,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    preference: dict,
    include_readme: bool,
    github_client: GitHubClient,
    ai_client: AIClient,
    task_id: str | None = None,
) -> tuple[int, int]:
    classified = 0
    failed = 0
    repo_datas: list[dict] = []
    readme_targets: list[dict] = []
    all_full_names: set[str] = set()
    success_full_names: set[str] = set()

    for repo in repos:
        if isinstance(repo, RepoBase):
            repo_data = repo.model_dump()
        else:
            repo_data = dict(repo)
        if include_readme and _should_fetch_readme(repo_data):
            readme_targets.append(repo_data)
        repo_datas.append(repo_data)
        full_name = repo_data.get("full_name")
        if full_name:
            all_full_names.add(full_name)

    if include_readme and readme_targets:
        async def fetch_readme(target: dict) -> dict:
            try:
                summary = await github_client.fetch_readme_summary(target["full_name"])
                return {"full_name": target["full_name"], "summary": summary, "success": True}
            except Exception as exc:
                logger.debug("README fetch failed for %s: %s", target.get("full_name"), exc)
                return {"full_name": target["full_name"], "summary": None, "success": False}

        results = await asyncio.gather(
            *(fetch_readme(target) for target in readme_targets),
            return_exceptions=True,
        )
        readme_updates: list[dict] = []
        for target, result in zip(readme_targets, results):
            if isinstance(result, Exception):
                logger.warning(
                    "README fetch raised unexpected exception for %s: %s",
                    target.get("full_name"),
                    result,
                )
                readme_updates.append(
                    {"full_name": target.get("full_name"), "summary": None, "success": False}
                )
                continue
            readme_updates.append(result)
            if result.get("success") and result.get("summary"):
                target["readme_summary"] = result["summary"]

        if readme_updates:
            try:
                await record_readme_fetches(readme_updates)
            except Exception as exc:
                logger.warning("Failed to persist README batch updates: %s", exc)
                for update in readme_updates:
                    full_name = update.get("full_name")
                    if not full_name:
                        continue
                    try:
                        await record_readme_fetch(
                            full_name,
                            update.get("summary"),
                            bool(update.get("success")),
                        )
                    except Exception:
                        logger.warning("Failed to record README fetch failure for %s", full_name)

    effective_rules = _apply_rule_priority_overrides(rules, preference)
    tag_mapping = _resolve_tag_mapping(data, preference)

    if CLASSIFY_ENGINE_V2_ENABLED:
        policy = DecisionPolicy(
            direct_rule_threshold=RULE_DIRECT_THRESHOLD,
            ai_required_threshold=RULE_AI_THRESHOLD,
        )
    else:
        policy = DecisionPolicy(direct_rule_threshold=0.0, ai_required_threshold=1.0)
    engine = ClassificationEngine(
        taxonomy=data,
        rules=effective_rules,
        classify_mode=classify_mode,
        use_ai=use_ai,
        policy=policy,
    )
    updates: list[dict] = []
    metric_classification_total = 0
    metric_rule_hit_total = 0
    metric_ai_fallback_total = 0
    metric_empty_tag_total = 0
    metric_uncategorized_total = 0

    for repo_data in repo_datas:
        full_name = repo_data.get("full_name")
        if not full_name:
            failed += 1
            continue
        started = time.perf_counter()
        try:
            outcome = await engine.classify_repo(repo_data, ai_client, ai_retries=2)
            result = _apply_tag_mapping_to_result(outcome.result, tag_mapping, data)
            provider = result.get("provider") if outcome.source == "ai" else "rules"
            model = result.get("model") if outcome.source == "ai" else "rules"
            if outcome.source == "manual_review":
                provider = "manual"
                model = "manual"
            updates.append(
                {
                    "full_name": full_name,
                    "category": result["category"],
                    "subcategory": result["subcategory"],
                    "confidence": result["confidence"],
                    "tags": result["tags"],
                    "tag_ids": result.get("tag_ids") or [],
                    "provider": provider,
                    "model": model,
                    "summary_zh": result.get("summary_zh"),
                    "keywords": result.get("keywords"),
                    "reason": str(result.get("reason") or outcome.reason or "")[:500],
                    "decision_source": outcome.source,
                    "rule_candidates": [
                        {
                            "rule_id": candidate.rule_id,
                            "score": candidate.score,
                            "category": candidate.category,
                            "subcategory": candidate.subcategory,
                            "evidence": candidate.evidence,
                            "tag_ids": candidate.tag_ids,
                        }
                        for candidate in outcome.rule_candidates[:5]
                    ],
                }
            )
            metric_classification_total += 1
            if outcome.source in ("rules", "rules_fallback"):
                metric_rule_hit_total += 1
            if outcome.source == "rules_fallback":
                metric_ai_fallback_total += 1
            if not result.get("tags"):
                metric_empty_tag_total += 1
            if str(result.get("category") or "") in ("uncategorized", "other", ""):
                metric_uncategorized_total += 1
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "classification_event %s",
                json.dumps(
                    {
                        "task_id": task_id,
                        "repo": full_name,
                        "rule_candidates": updates[-1]["rule_candidates"],
                        "final_decision": {
                            "source": outcome.source,
                            "category": result.get("category"),
                            "subcategory": result.get("subcategory"),
                            "confidence": result.get("confidence"),
                        },
                        "latency_ms": round(latency_ms, 2),
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning("Classification failed for %s: %s", full_name, exc)
            failed += 1

    if updates:
        try:
            await update_classifications_bulk(updates)
            classified += len(updates)
            for item in updates:
                if item.get("full_name"):
                    success_full_names.add(item["full_name"])
        except Exception as exc:
            logger.warning("Bulk classification update failed: %s", exc)
            for item in updates:
                full_name = item.get("full_name")
                if not full_name:
                    failed += 1
                    continue
                try:
                    await update_classification(
                        full_name,
                        item["category"],
                        item["subcategory"],
                        item["confidence"],
                        item["tags"],
                        item.get("tag_ids"),
                        item["provider"],
                        item["model"],
                        summary_zh=item.get("summary_zh"),
                        keywords=item.get("keywords"),
                        reason=item.get("reason"),
                        decision_source=item.get("decision_source"),
                        rule_candidates=item.get("rule_candidates"),
                    )
                    classified += 1
                    success_full_names.add(full_name)
                except Exception:
                    failed += 1

    failed_full_names = list(all_full_names - success_full_names)
    if failed_full_names:
        try:
            await increment_classify_fail_count(failed_full_names)
            logger.debug("Incremented fail count for %d repos", len(failed_full_names))
        except Exception as exc:
            logger.warning("Failed to increment classify_fail_count: %s", exc)

    if metric_classification_total > 0:
        await _add_quality_metrics(
            classification_total=metric_classification_total,
            rule_hit_total=metric_rule_hit_total,
            ai_fallback_total=metric_ai_fallback_total,
            empty_tag_total=metric_empty_tag_total,
            uncategorized_total=metric_uncategorized_total,
        )

    return (classified, failed)


async def _classify_repos_concurrent(
    repos_to_classify: list,
    data: dict,
    rules: list,
    classify_mode: str,
    use_ai: bool,
    preference: dict,
    include_readme: bool,
    concurrency: int,
    github_client: GitHubClient,
    ai_client: AIClient,
    task_id: str | None = None,
) -> tuple[int, int]:
    batches = _chunk_repos(repos_to_classify, AI_CLASSIFY_BATCH_SIZE)
    if concurrency <= 1 or len(batches) <= 1:
        classified = 0
        failed = 0
        for batch in batches:
            try:
                batch_classified, batch_failed = await _classify_repos_batch(
                    batch, data, rules, classify_mode, use_ai,
                    preference, include_readme, github_client, ai_client, task_id,
                )
                classified += batch_classified
                failed += batch_failed
            except Exception:
                failed += len(batch)
        return (classified, failed)

    classified = 0
    failed = 0
    counter_lock = asyncio.Lock()
    queue: asyncio.Queue[Optional[list]] = asyncio.Queue()
    for batch in batches:
        queue.put_nowait(batch)
    for _ in range(concurrency):
        queue.put_nowait(None)

    async def worker() -> None:
        nonlocal classified, failed
        while True:
            batch = await queue.get()
            if batch is None:
                queue.task_done()
                break
            try:
                batch_classified, batch_failed = await _classify_repos_batch(
                    batch, data, rules, classify_mode, use_ai,
                    preference, include_readme, github_client, ai_client, task_id,
                )
                async with counter_lock:
                    classified += batch_classified
                    failed += batch_failed
            except Exception:
                async with counter_lock:
                    failed += len(batch)
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await queue.join()
    await asyncio.gather(*workers)
    return (classified, failed)


# ---------------------------------------------------------------------------
# Background classify loop & start helper
# ---------------------------------------------------------------------------

async def _start_background_classify(
    payload: BackgroundClassifyRequest,
    task_id: str,
    allow_fallback: bool = False,
) -> bool:
    import api.app.state as _state
    async with classification_lock:
        if classification_state["running"]:
            return False
        classification_stop.clear()
        classification_state["running"] = True
        classification_state["task_id"] = task_id
        _state.classification_task = asyncio.create_task(
            _background_classify_loop(payload, allow_fallback, task_id)
        )
    return True


async def _background_classify_loop(
    payload: BackgroundClassifyRequest,
    allow_fallback: bool,
    task_id: str,
) -> None:
    from ..main import app

    try:
        await _set_task_status(task_id, "running", started_at=_now_iso())
        current = get_settings()
        rules_path = Path(__file__).resolve().parents[2] / "config" / "rules.json"
        rules = load_rules(current.rules_json, fallback_path=rules_path)
        classify_mode, use_ai, warning = _resolve_classify_context(
            current, rules, allow_fallback,
        )
        if warning:
            logger.warning("Background classification: %s", warning)

        should_run = use_ai or (classify_mode != "ai_only" and bool(rules))
        if not should_run:
            await _update_classification_state(
                running=False,
                finished_at=datetime.now(timezone.utc).isoformat(),
                processed=0, failed=0, remaining=0,
                last_error=warning or "No classification sources available",
                batch_size=0, concurrency=0, task_id=task_id,
            )
            await _set_task_status(
                task_id, "failed", finished_at=_now_iso(),
                message=warning or "No classification sources available",
            )
            return

        data = load_taxonomy(current.ai_taxonomy_path)
        preference_user = _normalize_preference_user(payload.preference_user)
        preference = await get_user_preferences(preference_user)
        github_client: GitHubClient = app.state.github_client
        ai_client: AIClient = app.state.ai_client

        requested_batch_size = payload.limit if payload.limit and payload.limit > 0 else DEFAULT_CLASSIFY_BATCH_SIZE
        batch_size = _clamp_batch_size(requested_batch_size)
        concurrency_value = payload.concurrency if payload.concurrency and payload.concurrency > 0 else DEFAULT_CLASSIFY_CONCURRENCY
        concurrency = _clamp_concurrency(concurrency_value)
        force_mode = bool(payload.force)
        cursor_full_name = payload.cursor_full_name if force_mode else None
        total_force = None
        if force_mode:
            total_force = await count_repos_for_classification(True, cursor_full_name)
            remaining = total_force
        else:
            remaining = await count_repos_for_classification(False)

        await _update_classification_state(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            processed=0, failed=0, remaining=remaining,
            last_error=None,
            batch_size=batch_size, concurrency=concurrency,
            task_id=task_id,
        )

        success_total = 0
        processed_total = 0
        failed_total = 0
        remaining_refresh_every = max(1, CLASSIFY_REMAINING_REFRESH_EVERY)
        refresh_counter = 0
        while not classification_stop.is_set():
            if force_mode:
                repos_to_classify = await select_repos_for_classification(
                    batch_size, True, cursor_full_name,
                )
            else:
                repos_to_classify = await select_repos_for_classification(batch_size, False)
            if not repos_to_classify:
                break

            batch_classified, batch_failed = await _classify_repos_concurrent(
                repos_to_classify, data, rules, classify_mode, use_ai,
                preference, payload.include_readme, concurrency,
                github_client, ai_client, task_id,
            )
            processed = batch_classified + batch_failed
            success_total += batch_classified
            processed_total += processed
            failed_total += batch_failed
            if force_mode:
                last_repo = repos_to_classify[-1]
                if isinstance(last_repo, RepoBase):
                    cursor_full_name = last_repo.full_name
                else:
                    cursor_full_name = last_repo.get("full_name")
                remaining = max(0, (total_force or 0) - processed_total)
                if cursor_full_name:
                    await _set_task_status(task_id, "running", cursor_full_name=cursor_full_name)
            else:
                refresh_counter += 1
                should_refresh = (
                    refresh_counter % remaining_refresh_every == 0 or
                    batch_failed > 0
                )
                if should_refresh:
                    remaining = await count_repos_for_classification(False)
                else:
                    remaining = max(0, remaining - batch_classified)
            state = await _get_classification_state()
            await _update_classification_state(
                processed=state["processed"] + processed,
                failed=state["failed"] + batch_failed,
                remaining=remaining,
            )

            if processed == 0:
                break
            if CLASSIFY_BATCH_DELAY_MS > 0:
                await asyncio.sleep(CLASSIFY_BATCH_DELAY_MS / 1000)

        await _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            task_id=None,
        )
        await _set_task_status(
            task_id, "finished", finished_at=_now_iso(),
            result={"processed": processed_total, "classified": success_total, "failed": failed_total},
        )
        await cache.invalidate_prefix("stats")
        await cache.invalidate_prefix("repos")
    except Exception as exc:
        state = await _get_classification_state()
        await _update_classification_state(
            running=False,
            finished_at=datetime.now(timezone.utc).isoformat(),
            processed=state.get("processed", 0),
            failed=state.get("failed", 0),
            remaining=state.get("remaining", 0),
            last_error=str(exc),
            batch_size=state.get("batch_size", 0),
            concurrency=state.get("concurrency", 0),
            task_id=None,
        )
        await _set_task_status(task_id, "failed", finished_at=_now_iso(), message=str(exc))


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.post("/classify", response_model=ClassifyResponse | TaskQueuedResponse, dependencies=[Depends(require_admin)])
@limiter.limit(RATE_LIMIT_HEAVY)
async def classify(request: Request, payload: ClassifyRequest) -> ClassifyResponse | TaskQueuedResponse:
    current = get_settings()
    try:
        data = load_taxonomy(current.ai_taxonomy_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.force:
        force_limit = 0 if payload.limit == 0 else _clamp_batch_size(payload.limit)
        task_id = str(uuid.uuid4())
        force_payload = BackgroundClassifyRequest(
            limit=force_limit,
            force=True,
            include_readme=payload.include_readme,
            preference_user=payload.preference_user,
            concurrency=DEFAULT_CLASSIFY_CONCURRENCY,
        )
        await _register_task(
            task_id, "classify", "Force classification queued",
            payload=force_payload.model_dump(),
        )
        started = await _start_background_classify(force_payload, task_id, allow_fallback=False)
        if not started:
            raise HTTPException(status_code=409, detail="Classification already running")
        response = TaskQueuedResponse(task_id=task_id, status="queued", message="Classification queued")
        return JSONResponse(status_code=202, content=response.model_dump())

    if payload.limit == 0:
        classify_limit = 0
    else:
        requested_limit = payload.limit if payload.limit > 0 else DEFAULT_CLASSIFY_BATCH_SIZE
        classify_limit = _clamp_batch_size(requested_limit)
    repos_to_classify = await select_repos_for_classification(classify_limit, payload.force)
    rules_path = Path(__file__).resolve().parents[2] / "config" / "rules.json"
    rules = load_rules(current.rules_json, fallback_path=rules_path)
    preference_user = _normalize_preference_user(payload.preference_user)
    preference = await get_user_preferences(preference_user)
    try:
        classify_mode, use_ai, warning = _resolve_classify_context(
            current, rules, allow_fallback=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if warning:
        logger.warning("Classification request: %s", warning)

    github_client: GitHubClient = request.app.state.github_client
    ai_client: AIClient = request.app.state.ai_client
    classified, failed = await _classify_repos_concurrent(
        repos_to_classify, data, rules, classify_mode, use_ai,
        preference, payload.include_readme,
        concurrency=1,
        github_client=github_client,
        ai_client=ai_client,
        task_id=None,
    )

    if repos_to_classify:
        await cache.invalidate_prefix("stats")
        await cache.invalidate_prefix("repos")

    return ClassifyResponse(
        total=len(repos_to_classify),
        classified=classified,
        failed=failed,
        remaining_unclassified=await count_unclassified_repos(),
    )


@router.post(
    "/classify/background",
    response_model=BackgroundClassifyResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
@limiter.limit(RATE_LIMIT_HEAVY)
async def classify_background(request: Request, payload: BackgroundClassifyRequest) -> BackgroundClassifyResponse:
    task_id = str(uuid.uuid4())
    await _register_task(
        task_id, "classify", "Background classification queued",
        payload=payload.model_dump(),
    )
    started = await _start_background_classify(payload, task_id, allow_fallback=False)
    if not started:
        raise HTTPException(status_code=409, detail="Classification already running")
    return BackgroundClassifyResponse(
        started=True,
        running=True,
        message="Background classification started",
        task_id=task_id,
    )


@router.get("/classify/status", response_model=BackgroundClassifyStatusResponse)
async def classify_status() -> BackgroundClassifyStatusResponse:
    state = await _get_classification_state()
    if not state.get("running"):
        state["task_id"] = None
    return BackgroundClassifyStatusResponse(**state)


@router.post("/classify/stop", dependencies=[Depends(require_admin)])
async def classify_stop() -> dict:
    classification_stop.set()
    await _update_classification_state(last_error="Stopped by user")
    return {"stopped": True}
