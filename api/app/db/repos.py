import json
from typing import Any, Dict, List, Optional, Tuple

from .helpers import _load_json_list, _retry_on_lock, _row_to_repo
from .pool import get_connection
from ..models import RepoBase


async def _load_star_users(repos: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    names = [repo.get("full_name") for repo in repos if repo.get("full_name")]
    if not names:
        return {}
    placeholders = ",".join("?" for _ in names)
    async with get_connection() as conn:
        rows = await (await conn.execute(
            f"SELECT full_name, star_users FROM repos WHERE full_name IN ({placeholders})",
            names,
        )).fetchall()
    existing: Dict[str, List[str]] = {}
    for row in rows:
        existing[row["full_name"]] = _load_json_list(row["star_users"])
    return existing


@_retry_on_lock()
async def upsert_repos(repos: List[Dict[str, Any]]) -> int:
    if not repos:
        return 0
    existing_users = await _load_star_users(repos)

    for repo in repos:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        current_users = set(existing_users.get(full_name, []))
        new_users = set(repo.get("star_users") or [])
        merged = sorted(current_users | new_users)
        repo["star_users"] = merged
    async with get_connection() as conn:
        await conn.executemany(
            """
            INSERT INTO repos (
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users
            ) VALUES (
                :full_name, :name, :owner, :html_url, :description, :language,
                :stargazers_count, :forks_count, :topics, :pushed_at, :updated_at, :starred_at,
                :star_users
            )
            ON CONFLICT(full_name) DO UPDATE SET
                name=excluded.name,
                owner=excluded.owner,
                html_url=excluded.html_url,
                description=excluded.description,
                language=excluded.language,
                stargazers_count=excluded.stargazers_count,
                forks_count=excluded.forks_count,
                topics=excluded.topics,
                pushed_at=excluded.pushed_at,
                updated_at=excluded.updated_at,
                starred_at=excluded.starred_at,
                star_users=excluded.star_users
            """,
            [
                {
                    **repo,
                    "topics": json.dumps(repo.get("topics") or []),
                    "star_users": json.dumps(repo.get("star_users") or []),
                }
                for repo in repos
            ],
        )
        await conn.commit()
    return len(repos)


async def get_repo(full_name: str) -> Optional[RepoBase]:
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users,
                category, subcategory, ai_confidence, ai_tags, ai_tag_ids, ai_provider, ai_model,
                ai_reason, ai_decision_source, ai_rule_candidates, ai_updated_at,
                override_category, override_subcategory, override_tags, override_tag_ids,
                override_note, readme_summary, readme_fetched_at,
                summary_zh, ai_keywords, override_summary_zh, override_keywords
            FROM repos
            WHERE full_name = ?
            """,
            (full_name,),
        )).fetchone()
        if not row:
            return None
    return _row_to_repo(row)


@_retry_on_lock()
async def prune_star_user(
    username: str, keep_full_names: List[str], delete_orphans: bool = True
) -> Tuple[int, int]:
    if not username:
        return (0, 0)
    keep_set = set(keep_full_names)
    removed = 0
    deleted = 0
    async with get_connection() as conn:
        rows = await (await conn.execute(
            "SELECT full_name, star_users FROM repos WHERE star_users LIKE ?",
            (f"%\"{username}\"%",),
        )).fetchall()
        for row in rows:
            full_name = row["full_name"]
            if full_name in keep_set:
                continue
            users = _load_json_list(row["star_users"])
            if username not in users:
                continue
            users = [user for user in users if user != username]
            if not users and delete_orphans:
                await conn.execute("DELETE FROM repos WHERE full_name = ?", (full_name,))
                deleted += 1
            else:
                await conn.execute(
                    "UPDATE repos SET star_users = ? WHERE full_name = ?",
                    (json.dumps(users), full_name),
                )
                removed += 1
        await conn.commit()
    return (removed, deleted)


@_retry_on_lock()
async def prune_users_not_in(
    allowed_users: List[str], delete_orphans: bool = True
) -> Tuple[int, int]:
    allowed_set = {user for user in allowed_users if user}
    if not allowed_set:
        return (0, 0)
    updated = 0
    deleted = 0
    async with get_connection() as conn:
        rows = await (await conn.execute("SELECT full_name, star_users FROM repos")).fetchall()
        for row in rows:
            users = _load_json_list(row["star_users"])
            filtered = [user for user in users if user in allowed_set]
            if filtered == users:
                continue
            if not filtered and delete_orphans:
                await conn.execute("DELETE FROM repos WHERE full_name = ?", (row["full_name"],))
                deleted += 1
            else:
                await conn.execute(
                    "UPDATE repos SET star_users = ? WHERE full_name = ?",
                    (json.dumps(filtered), row["full_name"]),
                )
                updated += 1
        await conn.commit()
    return (updated, deleted)


@_retry_on_lock()
async def record_readme_fetch(full_name: str, summary: Optional[str], success: bool) -> None:
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    async with get_connection() as conn:
        if success:
            if summary:
                await conn.execute(
                    """
                    UPDATE repos
                    SET readme_summary = ?, readme_fetched_at = ?, readme_last_attempt_at = ?,
                        readme_failures = 0, readme_empty = 0
                    WHERE full_name = ?
                    """,
                    (summary, timestamp, timestamp, full_name),
                )
            else:
                await conn.execute(
                    """
                    UPDATE repos
                    SET readme_summary = NULL,
                        readme_fetched_at = ?,
                        readme_last_attempt_at = ?,
                        readme_failures = 0,
                        readme_empty = 1
                    WHERE full_name = ?
                    """,
                    (timestamp, timestamp, full_name),
                )
        else:
            await conn.execute(
                """
                UPDATE repos
                SET readme_last_attempt_at = ?, readme_failures = COALESCE(readme_failures, 0) + 1
                WHERE full_name = ?
                """,
                (timestamp, full_name),
            )
        await conn.commit()


@_retry_on_lock()
async def record_readme_fetches(entries: List[Dict[str, Any]]) -> None:
    if not entries:
        return
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).isoformat()
    with_summary: List[tuple] = []
    empty_summary: List[tuple] = []
    failures: List[tuple] = []
    for entry in entries:
        full_name = entry.get("full_name")
        if not full_name:
            continue
        success = bool(entry.get("success"))
        summary = entry.get("summary") if success else None
        if success:
            if summary:
                with_summary.append((summary, timestamp, timestamp, full_name))
            else:
                empty_summary.append((timestamp, timestamp, full_name))
        else:
            failures.append((timestamp, full_name))
    async with get_connection() as conn:
        try:
            if with_summary:
                await conn.executemany(
                    """
                    UPDATE repos
                    SET readme_summary = ?, readme_fetched_at = ?, readme_last_attempt_at = ?,
                        readme_failures = 0, readme_empty = 0
                    WHERE full_name = ?
                    """,
                    with_summary,
                )
            if empty_summary:
                await conn.executemany(
                    """
                    UPDATE repos
                    SET readme_summary = NULL,
                        readme_fetched_at = ?,
                        readme_last_attempt_at = ?,
                        readme_failures = 0,
                        readme_empty = 1
                    WHERE full_name = ?
                    """,
                    empty_summary,
                )
            if failures:
                await conn.executemany(
                    """
                    UPDATE repos
                    SET readme_last_attempt_at = ?, readme_failures = COALESCE(readme_failures, 0) + 1
                    WHERE full_name = ?
                    """,
                    failures,
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
