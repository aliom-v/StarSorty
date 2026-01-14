import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

from .config import get_settings
from .taxonomy import format_taxonomy_for_prompt, validate_classification

logger = logging.getLogger("starsorty.ai")


def _default_base_url(provider: str) -> str:
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "anthropic":
        return "https://api.anthropic.com/v1"
    return ""


def _headers(provider: str) -> Dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if provider == "anthropic":
        if settings.ai_api_key:
            headers["x-api-key"] = settings.ai_api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        if settings.ai_api_key:
            headers["Authorization"] = f"Bearer {settings.ai_api_key}"
    if settings.ai_headers_json:
        try:
            extra = json.loads(settings.ai_headers_json)
            if isinstance(extra, dict):
                headers.update({str(k): str(v) for k, v in extra.items()})
        except json.JSONDecodeError:
            pass
    return headers


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        parts = candidate.split("```")
        if len(parts) >= 3:
            candidate = parts[1].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = candidate[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None


def _build_prompts(repo: Dict[str, Any], taxonomy_text: str, allowed_tags: List[str]) -> Dict[str, str]:
    repo_context = {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "description": repo.get("description"),
        "topics": repo.get("topics") or [],
        "readme_summary": repo.get("readme_summary"),
    }
    tags_line = ", ".join(allowed_tags) if allowed_tags else "free-form"
    system_prompt = (
        "You classify GitHub repositories into a fixed taxonomy.\n"
        "Return ONLY valid JSON with this schema:\n"
        '{\"category\":\"...\",\"subcategory\":\"...\",\"tags\":[\"...\"],\"confidence\":0.0}\n'
        "Rules:\n"
        "- category and subcategory must be from the taxonomy list.\n"
        "- Ignore programming language; classify by product functionality or use case.\n"
        "- If unsure, use category 'uncategorized' and subcategory 'other'.\n"
        "- tags must be chosen from the allowed tags list if provided; otherwise return [] or reasonable tags.\n"
        "- confidence is between 0 and 1.\n\n"
        "Taxonomy:\n"
        f"{taxonomy_text}\n\n"
        f"Allowed tags: {tags_line}\n"
    )
    user_prompt = json.dumps(repo_context, ensure_ascii=True)
    return {"system": system_prompt, "user": user_prompt}


def classify_repo(repo: Dict[str, Any], taxonomy: Dict[str, List[Dict[str, List[str]]]]) -> Dict[str, Any]:
    settings = get_settings()
    raw_provider = settings.ai_provider.lower()
    if raw_provider in ("", "none"):
        raise ValueError("AI_PROVIDER is not configured")
    if not settings.ai_model:
        raise ValueError("AI_MODEL is required for classification")

    provider = "anthropic" if raw_provider == "anthropic" else "openai"
    base_url = settings.ai_base_url or _default_base_url(raw_provider)
    if not base_url:
        raise ValueError("AI_BASE_URL is required for this provider")

    prompts = _build_prompts(
        repo,
        format_taxonomy_for_prompt(taxonomy),
        taxonomy.get("tags") or [],
    )
    headers = _headers(provider)
    payload: Dict[str, Any]
    url: str

    if provider == "anthropic":
        url = f"{base_url.rstrip('/')}/messages"
        payload = {
            "model": settings.ai_model,
            "system": prompts["system"],
            "messages": [{"role": "user", "content": prompts["user"]}],
            "max_tokens": settings.ai_max_tokens,
            "temperature": settings.ai_temperature,
        }
    else:
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": settings.ai_model,
            "messages": [
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": prompts["user"]},
            ],
            "max_tokens": settings.ai_max_tokens,
            "temperature": settings.ai_temperature,
        }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=settings.ai_timeout,
    )
    response.raise_for_status()

    data = response.json()
    if provider == "anthropic":
        content = data.get("content") or []
        text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        extracted = _extract_json(text)
    else:
        choices = data.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        extracted = _extract_json(message.get("content", ""))

    validated = validate_classification(extracted or {}, taxonomy)
    validated["provider"] = raw_provider
    validated["model"] = settings.ai_model
    return validated


def classify_repo_with_retry(
    repo: Dict[str, Any],
    taxonomy: Dict[str, List[Dict[str, List[str]]]],
    retries: int = 2,
) -> Dict[str, Any]:
    attempt = 0
    while True:
        try:
            return classify_repo(repo, taxonomy)
        except Exception as exc:
            if attempt >= retries:
                logger.warning(
                    "AI classify failed after %s attempts: %s",
                    attempt + 1,
                    exc,
                )
                raise exc
            wait = 2 ** attempt
            logger.warning(
                "AI classify failed on attempt %s/%s: %s. Retrying in %ss",
                attempt + 1,
                retries + 1,
                exc,
                wait,
            )
            time.sleep(wait)
            attempt += 1
