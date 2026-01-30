from datetime import datetime, timezone
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import get_settings
from .models import RepoBase

logger = logging.getLogger("starsorty.github")
GITHUB_API_BASE_URL = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com").rstrip("/")
_rate_limit_lock = asyncio.Lock()
_rate_limit_reset_at: Optional[float] = None


async def _sleep_if_rate_limited() -> None:
    async with _rate_limit_lock:
        reset_at = _rate_limit_reset_at
    # Note: Using snapshot value outside lock is intentional - sleeping inside
    # the lock would block other coroutines. The TOCTOU here is benign.
    if reset_at:
        now = time.time()
        if now < reset_at:
            wait = reset_at - now
            logger.warning("GitHub rate limit active, sleeping for %.1fs", wait)
            await asyncio.sleep(wait)


async def _set_rate_limit_reset(reset_header: Optional[str]) -> None:
    if not reset_header:
        return
    try:
        reset_at = float(int(reset_header))
    except (TypeError, ValueError):
        return
    async with _rate_limit_lock:
        global _rate_limit_reset_at
        if not _rate_limit_reset_at or reset_at > _rate_limit_reset_at:
            _rate_limit_reset_at = reset_at


def _next_link(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None
    parts = link_header.split(",")
    for part in parts:
        section = part.strip()
        if 'rel="next"' in section:
            url = section.split(";")[0].strip()
            return url.strip("<>")
    return None


def _normalize_repo(repo: Dict[str, Any], starred_at: Optional[str]) -> RepoBase:
    owner = repo.get("owner") or {}
    topics = repo.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    pushed_at = _normalize_timestamp(repo.get("pushed_at"))
    updated_at = _normalize_timestamp(repo.get("updated_at"))
    starred_at_norm = _normalize_timestamp(starred_at)
    return RepoBase(
        full_name=repo.get("full_name") or "",
        name=repo.get("name") or "",
        owner=owner.get("login") or "",
        html_url=repo.get("html_url") or "",
        description=repo.get("description"),
        language=repo.get("language"),
        stargazers_count=int(repo.get("stargazers_count") or 0),
        forks_count=int(repo.get("forks_count") or 0),
        topics=topics,
        pushed_at=pushed_at,
        updated_at=updated_at,
        starred_at=starred_at_norm,
    )


def _normalize_timestamp(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.astimezone(timezone.utc).isoformat()


def _default_headers() -> Dict[str, str]:
    settings = get_settings()
    headers = {
        "Accept": "application/vnd.github.star+json",
        "User-Agent": "StarSorty",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    retries: int = 2,
) -> httpx.Response:
    for attempt in range(retries + 1):
        await _sleep_if_rate_limited()
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
        except httpx.RequestError as exc:
            if attempt >= retries:
                raise exc
            wait = 2 ** attempt
            logger.warning(
                "GitHub request error on attempt %s/%s: %s. Retrying in %ss",
                attempt + 1,
                retries + 1,
                exc,
                wait,
            )
            await asyncio.sleep(wait)
            continue

        rate_limited = (
            response.status_code == 403
            and response.headers.get("X-RateLimit-Remaining") == "0"
        )
        retryable = response.status_code in (429, 500, 502, 503, 504) or rate_limited

        if rate_limited:
            reset_header = response.headers.get("X-RateLimit-Reset")
            await _set_rate_limit_reset(reset_header)
            if reset_header:
                reset_at = float(int(reset_header))
                wait = max(1.0, reset_at - time.time())
            else:
                wait = max(1.0, 2 ** attempt)
            logger.warning(
                "GitHub rate limit hit (status %s). Sleeping for %.1fs before retry.",
                response.status_code,
                wait,
            )
            await asyncio.sleep(wait)
            if attempt < retries:
                continue
            return response

        if retryable and attempt < retries:
            wait = 2 ** attempt
            logger.warning(
                "GitHub request status %s on attempt %s/%s. Retrying in %ss",
                response.status_code,
                attempt + 1,
                retries + 1,
                wait,
            )
            await asyncio.sleep(wait)
            continue

        return response

    # This line is unreachable due to the loop structure, but kept for safety
    return response  # pragma: no cover


def _parse_usernames(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [item.strip() for item in raw.replace("\n", ",").split(",")]
    return [item for item in parts if item]


class GitHubClient:
    def __init__(self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> None:
        self._client = client
        self._semaphore = semaphore

    async def fetch_authenticated_login(self) -> str:
        settings = get_settings()
        if not settings.github_token:
            raise ValueError("GITHUB_TOKEN is required to fetch the authenticated user")
        async with self._semaphore:
            response = await _request_with_retry(
                self._client,
                "GET",
                f"{GITHUB_API_BASE_URL}/user",
                headers=_default_headers(),
                timeout=30,
            )
        if response.status_code == 401:
            raise ValueError("GitHub authentication failed. Check GITHUB_TOKEN.")
        response.raise_for_status()
        data = response.json()
        login = data.get("login")
        if not login:
            raise ValueError("Unable to resolve authenticated username")
        return str(login)

    async def resolve_targets(self) -> List[Tuple[str, bool]]:
        settings = get_settings()
        targets: List[Tuple[str, bool]] = []

        usernames = _parse_usernames(settings.github_usernames)
        if settings.github_target_username:
            usernames.append(settings.github_target_username)
        if settings.github_username:
            usernames.append(settings.github_username)

        for name in usernames:
            targets.append((name, False))

        if settings.github_token and (settings.github_include_self or not targets):
            login = await self.fetch_authenticated_login()
            targets.append((login, True))

        if not targets:
            raise ValueError("No GitHub usernames configured")

        deduped: Dict[str, Tuple[str, bool]] = {}
        for name, use_auth in targets:
            existing = deduped.get(name)
            if not existing or (use_auth and not existing[1]):
                deduped[name] = (name, use_auth)
        return list(deduped.values())

    async def fetch_starred_repos_for_user(self, username: str, use_auth: bool) -> List[RepoBase]:
        settings = get_settings()
        if use_auth and not settings.github_token:
            raise ValueError("GITHUB_TOKEN is required for authenticated sync")

        if use_auth:
            url = f"{GITHUB_API_BASE_URL}/user/starred"
        else:
            url = f"{GITHUB_API_BASE_URL}/users/{username}/starred"

        params = {"per_page": 100}
        next_url = url
        is_first = True
        results: List[RepoBase] = []

        while next_url:
            async with self._semaphore:
                response = await _request_with_retry(
                    self._client,
                    "GET",
                    next_url,
                    headers=_default_headers(),
                    params=params if is_first else None,
                    timeout=30,
                )
            if response.status_code == 401:
                raise ValueError("GitHub authentication failed. Check GITHUB_TOKEN.")
            response.raise_for_status()

            payload = response.json()
            for item in payload:
                if isinstance(item, dict) and "repo" in item:
                    repo = item.get("repo") or {}
                    starred_at = item.get("starred_at")
                else:
                    repo = item
                    starred_at = None
                normalized = _normalize_repo(repo, starred_at)
                if normalized.full_name:
                    results.append(normalized)

            next_url = _next_link(response.headers.get("Link"))
            is_first = False

        return results

    async def fetch_readme_summary(self, full_name: str, max_chars: int = 1500) -> str:
        settings = get_settings()
        headers = {
            "Accept": "application/vnd.github.raw",
            "User-Agent": "StarSorty",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        url = f"{GITHUB_API_BASE_URL}/repos/{full_name}/readme"
        async with self._semaphore:
            response = await _request_with_retry(self._client, "GET", url, headers=headers, timeout=30)
        if response.status_code == 404:
            return ""
        if response.status_code == 401:
            raise ValueError("GitHub authentication failed. Check GITHUB_TOKEN.")
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[:max_chars]
