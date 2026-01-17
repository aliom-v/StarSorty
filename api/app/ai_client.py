import json
import logging
import re
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


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "token",
    "secret",
    "password",
    "x-api-key",
}


def _mask_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) <= 4:
            return "****"
        return f"{value[:2]}***{value[-2:]}"
    return "***"


def _mask_sensitive_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        masked: Dict[str, Any] = {}
        for key, value in payload.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                masked[key] = _mask_value(value)
            else:
                masked[key] = _mask_sensitive_payload(value)
        return masked
    if isinstance(payload, list):
        return [_mask_sensitive_payload(item) for item in payload]
    return payload


def _mask_secrets_in_text(text: str) -> str:
    masked = text
    masked = re.sub(r"(?i)(authorization\\s*[:=]\\s*bearer\\s+)[^\\s\"']+", r"\\1***", masked)
    masked = re.sub(r"(?i)(x-api-key\\s*[:=]\\s*)[^\\s\"']+", r"\\1***", masked)
    masked = re.sub(r"(?i)(api_key\\s*[:=]\\s*)[^\\s\"']+", r"\\1***", masked)
    masked = re.sub(r"\\bsk-[A-Za-z0-9\\-]{8,}\\b", "sk-***", masked)
    return masked


def _sanitize_response_body(text: str) -> str:
    if not text:
        return ""
    trimmed = text.strip()
    if not trimmed:
        return ""
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return _mask_secrets_in_text(trimmed)
    masked = _mask_sensitive_payload(parsed)
    try:
        return json.dumps(masked, ensure_ascii=True)
    except (TypeError, ValueError):
        return _mask_secrets_in_text(trimmed)


def _raise_for_status_with_detail(response: requests.Response, url: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = _sanitize_response_body(response.text)
        if detail:
            if len(detail) > 800:
                detail = detail[:800] + "..."
            raise requests.HTTPError(
                f"{exc} | url={url} | body={detail}"
            ) from exc
        raise requests.HTTPError(f"{exc} | url={url}") from exc


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
    _raise_for_status_with_detail(response, url)

    try:
        data = response.json()
    except ValueError as exc:
        detail = _sanitize_response_body(response.text)
        if len(detail) > 800:
            detail = detail[:800] + "..."
        raise ValueError(
            f"AI response JSON decode failed (status {response.status_code}) | url={url} | body={detail}"
        ) from exc
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
