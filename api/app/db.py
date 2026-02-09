import asyncio
import functools
import json
import logging
import math
import os
import random
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiosqlite

from .config import get_settings
from .models import RepoBase
from .search.ranker import rank_repo_matches

logger = logging.getLogger("starsorty.db")
_pool: "SQLitePool | None" = None
_fts_enabled = False


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r, fallback to %s", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("Out-of-range %s=%r, fallback to %s", name, raw, default)
        return default
    return value


FTS_MAX_TERMS = _env_int("FTS_MAX_TERMS", 8, minimum=1)


def _retry_on_lock(
    max_attempts: int = 5,
    base_delay: float = 0.05,
    max_delay: float = 0.5,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    message = str(exc).lower()
                    if "database is locked" not in message and "database table is locked" not in message:
                        raise
                    if attempt >= max_attempts - 1:
                        raise
                    delay = min(max_delay, base_delay * (2**attempt))
                    jitter = random.uniform(0, delay)
                    logger.warning("SQLite locked, retrying in %.2fs", delay + jitter)
                    await asyncio.sleep(delay + jitter)
                    attempt += 1
        return wrapper

    return decorator

def _sqlite_path(database_url: str) -> str:
    if database_url.startswith("sqlite:////"):
        return "/" + database_url[len("sqlite:////"):]
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///"):]
    raise ValueError("Only sqlite is supported in the skeleton")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _build_fts_query(raw_query: str) -> str | None:
    terms = [
        term.strip().lower()
        for term in re.split(r"[^\w\u4e00-\u9fff]+", raw_query)
        if term and term.strip()
    ]
    if not terms:
        return None
    normalized: List[str] = []
    for term in terms[:FTS_MAX_TERMS]:
        escaped = term[:64].replace('"', '""')
        if escaped:
            normalized.append(f'"{escaped}"')
    if not normalized:
        return None
    return " AND ".join(normalized)


async def _init_repos_fts(conn: aiosqlite.Connection) -> None:
    global _fts_enabled
    try:
        # Recreate FTS table/triggers to keep schema in sync across upgrades.
        await conn.execute("DROP TRIGGER IF EXISTS repos_ai")
        await conn.execute("DROP TRIGGER IF EXISTS repos_ad")
        await conn.execute("DROP TRIGGER IF EXISTS repos_au")
        await conn.execute("DROP TABLE IF EXISTS repos_fts")
        await conn.execute(
            """
            CREATE VIRTUAL TABLE repos_fts USING fts5(
                full_name,
                name,
                description,
                topics,
                readme_summary,
                ai_tags,
                ai_tag_ids,
                override_tags,
                override_tag_ids,
                star_users,
                summary_zh,
                override_summary_zh,
                ai_keywords,
                override_keywords,
                content='repos',
                content_rowid='id'
            )
            """
        )
        await conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS repos_ai AFTER INSERT ON repos BEGIN
                INSERT INTO repos_fts(
                    rowid,
                    full_name,
                    name,
                    description,
                    topics,
                    readme_summary,
                    ai_tags,
                    ai_tag_ids,
                    override_tags,
                    override_tag_ids,
                    star_users,
                    summary_zh,
                    override_summary_zh,
                    ai_keywords,
                    override_keywords
                ) VALUES (
                    new.id,
                    new.full_name,
                    new.name,
                    new.description,
                    new.topics,
                    new.readme_summary,
                    new.ai_tags,
                    new.ai_tag_ids,
                    new.override_tags,
                    new.override_tag_ids,
                    new.star_users,
                    new.summary_zh,
                    new.override_summary_zh,
                    new.ai_keywords,
                    new.override_keywords
                );
            END;
            """
        )
        await conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS repos_ad AFTER DELETE ON repos BEGIN
                INSERT INTO repos_fts(
                    repos_fts,
                    rowid,
                    full_name,
                    name,
                    description,
                    topics,
                    readme_summary,
                    ai_tags,
                    ai_tag_ids,
                    override_tags,
                    override_tag_ids,
                    star_users,
                    summary_zh,
                    override_summary_zh,
                    ai_keywords,
                    override_keywords
                ) VALUES (
                    'delete',
                    old.id,
                    old.full_name,
                    old.name,
                    old.description,
                    old.topics,
                    old.readme_summary,
                    old.ai_tags,
                    old.ai_tag_ids,
                    old.override_tags,
                    old.override_tag_ids,
                    old.star_users,
                    old.summary_zh,
                    old.override_summary_zh,
                    old.ai_keywords,
                    old.override_keywords
                );
            END;
            """
        )
        await conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS repos_au AFTER UPDATE ON repos BEGIN
                INSERT INTO repos_fts(
                    repos_fts,
                    rowid,
                    full_name,
                    name,
                    description,
                    topics,
                    readme_summary,
                    ai_tags,
                    ai_tag_ids,
                    override_tags,
                    override_tag_ids,
                    star_users,
                    summary_zh,
                    override_summary_zh,
                    ai_keywords,
                    override_keywords
                ) VALUES (
                    'delete',
                    old.id,
                    old.full_name,
                    old.name,
                    old.description,
                    old.topics,
                    old.readme_summary,
                    old.ai_tags,
                    old.ai_tag_ids,
                    old.override_tags,
                    old.override_tag_ids,
                    old.star_users,
                    old.summary_zh,
                    old.override_summary_zh,
                    old.ai_keywords,
                    old.override_keywords
                );
                INSERT INTO repos_fts(
                    rowid,
                    full_name,
                    name,
                    description,
                    topics,
                    readme_summary,
                    ai_tags,
                    ai_tag_ids,
                    override_tags,
                    override_tag_ids,
                    star_users,
                    summary_zh,
                    override_summary_zh,
                    ai_keywords,
                    override_keywords
                ) VALUES (
                    new.id,
                    new.full_name,
                    new.name,
                    new.description,
                    new.topics,
                    new.readme_summary,
                    new.ai_tags,
                    new.ai_tag_ids,
                    new.override_tags,
                    new.override_tag_ids,
                    new.star_users,
                    new.summary_zh,
                    new.override_summary_zh,
                    new.ai_keywords,
                    new.override_keywords
                );
            END;
            """
        )

        repos_total = (await (await conn.execute("SELECT COUNT(*) FROM repos")).fetchone())[0]
        fts_total = (await (await conn.execute("SELECT COUNT(*) FROM repos_fts")).fetchone())[0]
        if repos_total != fts_total:
            logger.info(
                "Rebuilding repos_fts index (repos=%s, fts=%s)",
                repos_total,
                fts_total,
            )
            await conn.execute("INSERT INTO repos_fts(repos_fts) VALUES ('rebuild')")

        _fts_enabled = True
    except sqlite3.OperationalError as exc:
        _fts_enabled = False
        logger.warning("SQLite FTS5 unavailable, falling back to LIKE search: %s", exc)


# SQLite configuration from environment
SQLITE_JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "WAL").upper()
SQLITE_SYNCHRONOUS = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL").upper()
SQLITE_BUSY_TIMEOUT = _env_int("SQLITE_BUSY_TIMEOUT", 5000, minimum=1)


async def _configure_connection(conn: aiosqlite.Connection) -> None:
    """Configure SQLite connection for optimal performance.

    Configurable via environment variables:
    - SQLITE_JOURNAL_MODE: WAL (default), DELETE, TRUNCATE, PERSIST, MEMORY, OFF
    - SQLITE_SYNCHRONOUS: NORMAL (default), FULL, OFF
    - SQLITE_BUSY_TIMEOUT: 5000ms (default)
    """
    try:
        # Set journal mode and log effective value
        result = await conn.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE}")
        row = await result.fetchone()
        effective_mode = row[0] if row else "unknown"
        if effective_mode.upper() != SQLITE_JOURNAL_MODE:
            logger.warning(
                "SQLite journal_mode: requested %s, got %s",
                SQLITE_JOURNAL_MODE,
                effective_mode,
            )
        else:
            logger.debug("SQLite journal_mode: %s", effective_mode)

        await conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS}")
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT}")
    except Exception as exc:
        logger.warning("Failed to apply SQLite pragmas: %s", exc)


class SQLitePool:
    def __init__(self, db_path: str, size: int) -> None:
        self._db_path = db_path
        self._size = max(1, size)
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=self._size)

    async def init(self) -> None:
        for _ in range(self._size):
            conn = await aiosqlite.connect(self._db_path, timeout=30)
            conn.row_factory = aiosqlite.Row
            await _configure_connection(conn)
            await self._pool.put(conn)

    async def close(self) -> None:
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()

    @asynccontextmanager
    async def connection(self) -> aiosqlite.Connection:
        conn = await self._pool.get()
        try:
            yield conn
        finally:
            await self._pool.put(conn)


async def init_db_pool(pool_size: Optional[int] = None) -> None:
    global _pool
    if pool_size is None:
        pool_size = _env_int("DB_POOL_SIZE", 5, minimum=1)
    settings = get_settings()
    db_path = _sqlite_path(settings.database_url)
    _ensure_parent_dir(db_path)
    pool = SQLitePool(db_path, pool_size)
    await pool.init()
    _pool = pool


async def close_db_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
    _pool = None


@asynccontextmanager
async def get_connection() -> aiosqlite.Connection:
    if _pool is None:
        settings = get_settings()
        db_path = _sqlite_path(settings.database_url)
        _ensure_parent_dir(db_path)
        conn = await aiosqlite.connect(db_path, timeout=30)
        conn.row_factory = aiosqlite.Row
        await _configure_connection(conn)
        try:
            yield conn
        finally:
            await conn.close()
        return
    async with _pool.connection() as conn:
        yield conn


@_retry_on_lock()
async def init_db() -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_at TEXT,
                last_result TEXT,
                last_message TEXT
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                html_url TEXT NOT NULL,
                description TEXT,
                language TEXT,
                stargazers_count INTEGER,
                forks_count INTEGER,
                topics TEXT,
                pushed_at TEXT,
                updated_at TEXT,
                starred_at TEXT,
                star_users TEXT,
                category TEXT,
                subcategory TEXT,
                ai_confidence REAL,
                ai_tags TEXT,
                ai_tag_ids TEXT,
                ai_provider TEXT,
                ai_model TEXT,
                ai_reason TEXT,
                ai_decision_source TEXT,
                ai_rule_candidates TEXT,
                ai_updated_at TEXT,
                override_category TEXT,
                override_subcategory TEXT,
                override_tags TEXT,
                override_tag_ids TEXT,
                override_note TEXT,
                readme_summary TEXT,
                readme_fetched_at TEXT,
                readme_last_attempt_at TEXT,
                readme_failures INTEGER,
                readme_empty INTEGER
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS override_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                category TEXT,
                subcategory TEXT,
                tags TEXT,
                note TEXT,
                updated_at TEXT
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                message TEXT,
                result TEXT,
                cursor_full_name TEXT,
                payload TEXT,
                retry_from_task_id TEXT
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                tag_mapping_json TEXT NOT NULL DEFAULT '{}',
                rule_priority_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                query TEXT,
                full_name TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_interest_profiles (
                user_id TEXT PRIMARY KEY,
                topic_scores TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                full_name TEXT NOT NULL,
                before_category TEXT,
                before_subcategory TEXT,
                before_tag_ids TEXT,
                after_category TEXT,
                after_subcategory TEXT,
                after_tag_ids TEXT,
                note TEXT,
                source TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await _ensure_columns(conn)
        await _ensure_task_columns(conn)
        await _init_repos_fts(conn)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repos(full_name)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_language ON repos(language)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_category ON repos(category)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_override_category ON repos(override_category)"
        )
        # Separate indexes for classification queue - SQLite can combine them
        # Index for sorting unclassified repos by priority
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_classify_sort ON repos(category, pushed_at DESC, stargazers_count DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_override_history_full_name ON override_history(full_name)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_updated_at ON tasks(status, updated_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_feedback_user_created ON user_feedback_events(user_id, created_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_training_samples_user_created ON training_samples(user_id, created_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_ai_keywords ON repos(ai_keywords)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_ai_tag_ids ON repos(ai_tag_ids)"
        )
        # Index for stargazers_count sorting (used in most queries)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_stargazers ON repos(stargazers_count DESC)"
        )
        # Composite index to support stable sorted pagination by stars/full_name
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_stargazers_full_name ON repos(stargazers_count DESC, full_name ASC)"
        )
        # Index for summary_zh search
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_summary_zh ON repos(summary_zh)"
        )
        await conn.execute(
            """
            INSERT OR IGNORE INTO sync_status (id, last_sync_at, last_result, last_message)
            VALUES (1, NULL, NULL, NULL)
            """
        )
        await conn.commit()


async def get_sync_status() -> dict:
    async with get_connection() as conn:
        row = await (await conn.execute(
            "SELECT last_sync_at, last_result, last_message FROM sync_status WHERE id = 1"
        )).fetchone()
        if row is None:
            return {"last_sync_at": None, "last_result": None, "last_message": None}
        return {
            "last_sync_at": row[0],
            "last_result": row[1],
            "last_message": row[2],
        }


@_retry_on_lock()
async def update_sync_status(result: str, message: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE sync_status
            SET last_sync_at = ?, last_result = ?, last_message = ?
            WHERE id = 1
            """,
            (timestamp, result, message),
        )
        await conn.commit()
    return timestamp


@_retry_on_lock()
async def create_task(
    task_id: str,
    task_type: str,
    status: str = "queued",
    message: str | None = None,
    payload: dict | None = None,
    retry_from_task_id: str | None = None,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload) if payload is not None else None
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO tasks (
                task_id,
                task_type,
                status,
                created_at,
                updated_at,
                message,
                payload,
                retry_from_task_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                status,
                timestamp,
                timestamp,
                message,
                payload_json,
                retry_from_task_id,
            ),
        )
        await conn.commit()


@_retry_on_lock()
async def update_task(
    task_id: str,
    status: str,
    *,
    started_at: str | None = None,
    finished_at: str | None = None,
    message: str | None = None,
    result: dict | None = None,
    cursor_full_name: str | None = None,
) -> None:
    fields = ["status = ?", "updated_at = ?"]
    params: List[Any] = [status, datetime.now(timezone.utc).isoformat()]
    if started_at is not None:
        fields.append("started_at = ?")
        params.append(started_at)
    if finished_at is not None:
        fields.append("finished_at = ?")
        params.append(finished_at)
    if message is not None:
        fields.append("message = ?")
        params.append(message)
    if result is not None:
        fields.append("result = ?")
        params.append(json.dumps(result))
    if cursor_full_name is not None:
        fields.append("cursor_full_name = ?")
        params.append(cursor_full_name)
    params.append(task_id)
    async with get_connection() as conn:
        await conn.execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?",
            params,
        )
        await conn.commit()


async def get_task(task_id: str) -> Dict[str, Any] | None:
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT
                task_id,
                task_type,
                status,
                created_at,
                updated_at,
                started_at,
                finished_at,
                message,
                result,
                cursor_full_name,
                payload,
                retry_from_task_id
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        )).fetchone()
    if not row:
        return None
    result: dict | None = None
    raw_result = row["result"]
    if raw_result:
        try:
            parsed = json.loads(raw_result)
            if isinstance(parsed, dict):
                result = parsed
        except json.JSONDecodeError:
            result = None
    return {
        "task_id": row["task_id"],
        "task_type": row["task_type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "message": row["message"],
        "result": result,
        "cursor_full_name": row["cursor_full_name"],
        "payload": _load_json_object(row["payload"]),
        "retry_from_task_id": row["retry_from_task_id"],
    }


@_retry_on_lock()
async def reset_stale_tasks(max_age_minutes: int = 10) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    cutoff_iso = cutoff.isoformat()
    timestamp = datetime.now(timezone.utc).isoformat()
    note = "stale task reset at startup"
    async with get_connection() as conn:
        cur = await conn.execute(
            """
            UPDATE tasks
            SET status = ?,
                finished_at = ?,
                updated_at = ?,
                message = CASE
                    WHEN message IS NULL OR message = '' THEN ?
                    ELSE message
                END
            WHERE status IN ('running', 'processing')
              AND COALESCE(updated_at, created_at) < ?
            """,
            ("failed", timestamp, timestamp, note, cutoff_iso),
        )
        await conn.commit()
        return int(cur.rowcount or 0)


async def _ensure_columns(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(repos)")
    rows = await cursor.fetchall()
    existing = {row["name"] for row in rows}
    columns = [
        ("star_users", "star_users TEXT"),
        ("category", "category TEXT"),
        ("subcategory", "subcategory TEXT"),
        ("ai_confidence", "ai_confidence REAL"),
        ("ai_tags", "ai_tags TEXT"),
        ("ai_tag_ids", "ai_tag_ids TEXT"),
        ("ai_provider", "ai_provider TEXT"),
        ("ai_model", "ai_model TEXT"),
        ("ai_reason", "ai_reason TEXT"),
        ("ai_decision_source", "ai_decision_source TEXT"),
        ("ai_rule_candidates", "ai_rule_candidates TEXT"),
        ("ai_updated_at", "ai_updated_at TEXT"),
        ("override_category", "override_category TEXT"),
        ("override_subcategory", "override_subcategory TEXT"),
        ("override_tags", "override_tags TEXT"),
        ("override_tag_ids", "override_tag_ids TEXT"),
        ("override_note", "override_note TEXT"),
        ("readme_summary", "readme_summary TEXT"),
        ("readme_fetched_at", "readme_fetched_at TEXT"),
        ("readme_last_attempt_at", "readme_last_attempt_at TEXT"),
        ("readme_failures", "readme_failures INTEGER"),
        ("readme_empty", "readme_empty INTEGER"),
        ("summary_zh", "summary_zh TEXT"),
        ("ai_keywords", "ai_keywords TEXT"),
        ("override_summary_zh", "override_summary_zh TEXT"),
        ("override_keywords", "override_keywords TEXT"),
        ("classify_fail_count", "classify_fail_count INTEGER DEFAULT 0"),
    ]
    for name, ddl in columns:
        if name not in existing:
            await conn.execute(f"ALTER TABLE repos ADD COLUMN {ddl}")


async def _ensure_task_columns(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(tasks)")
    rows = await cursor.fetchall()
    existing = {row["name"] for row in rows}
    columns = [
        ("payload", "payload TEXT"),
        ("retry_from_task_id", "retry_from_task_id TEXT"),
    ]
    for name, ddl in columns:
        if name not in existing:
            await conn.execute(f"ALTER TABLE tasks ADD COLUMN {ddl}")


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


def _load_json_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
        if isinstance(loaded, list):
            return [str(item) for item in loaded if item]
    except json.JSONDecodeError:
        return []
    return []


def _load_json_list_optional(value: Optional[str]) -> Optional[List[str]]:
    if value is None or value == "":
        return None
    return _load_json_list(value)


def _load_json_dict_list(value: Optional[str]) -> List[Dict[str, Any]]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    result: List[Dict[str, Any]] = []
    for item in loaded:
        if isinstance(item, dict):
            result.append(item)
    return result


def _load_json_object(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        return None
    return None


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


def _row_to_repo(row: aiosqlite.Row, include_internal: bool = False) -> RepoBase:
    topics = _load_json_list(row["topics"])
    star_users = _load_json_list(row["star_users"])
    ai_tags = _load_json_list(row["ai_tags"])
    ai_tag_ids = _load_json_list(row["ai_tag_ids"]) if "ai_tag_ids" in row.keys() else []
    override_tags = _load_json_list_optional(row["override_tags"])
    override_tag_ids = (
        _load_json_list_optional(row["override_tag_ids"]) if "override_tag_ids" in row.keys() else None
    )
    ai_keywords = _load_json_list(row["ai_keywords"]) if "ai_keywords" in row.keys() else []
    override_keywords = _load_json_list_optional(row["override_keywords"]) if "override_keywords" in row.keys() else None
    ai_rule_candidates = (
        _load_json_dict_list(row["ai_rule_candidates"]) if "ai_rule_candidates" in row.keys() else []
    )
    effective_category = row["override_category"] or row["category"]
    effective_subcategory = row["override_subcategory"] or row["subcategory"]
    effective_tags = ai_tags if override_tags is None else override_tags
    effective_tag_ids = ai_tag_ids if override_tag_ids is None else override_tag_ids
    effective_summary_zh = (row["override_summary_zh"] or row["summary_zh"]) if "summary_zh" in row.keys() else None
    effective_keywords = ai_keywords if override_keywords is None else override_keywords
    search_score = None
    if "search_score" in row.keys():
        try:
            search_score = float(row["search_score"])
        except (TypeError, ValueError):
            search_score = None
    match_reasons = _load_json_list(row["match_reasons"]) if "match_reasons" in row.keys() else []
    repo = RepoBase(
        full_name=row["full_name"],
        name=row["name"],
        owner=row["owner"],
        html_url=row["html_url"],
        description=row["description"],
        language=row["language"],
        stargazers_count=row["stargazers_count"],
        forks_count=row["forks_count"],
        topics=topics,
        star_users=star_users,
        category=effective_category,
        subcategory=effective_subcategory,
        tags=effective_tags,
        tag_ids=effective_tag_ids,
        ai_category=row["category"],
        ai_subcategory=row["subcategory"],
        ai_confidence=row["ai_confidence"],
        ai_tags=ai_tags,
        ai_tag_ids=ai_tag_ids,
        ai_keywords=ai_keywords,
        ai_provider=row["ai_provider"],
        ai_model=row["ai_model"],
        ai_reason=row["ai_reason"] if "ai_reason" in row.keys() else None,
        ai_decision_source=row["ai_decision_source"] if "ai_decision_source" in row.keys() else None,
        ai_rule_candidates=ai_rule_candidates,
        ai_updated_at=row["ai_updated_at"],
        override_category=row["override_category"],
        override_subcategory=row["override_subcategory"],
        override_tags=override_tags or [],
        override_tag_ids=override_tag_ids or [],
        override_note=row["override_note"],
        override_summary_zh=row["override_summary_zh"] if "override_summary_zh" in row.keys() else None,
        override_keywords=override_keywords or [],
        readme_summary=row["readme_summary"],
        readme_fetched_at=row["readme_fetched_at"],
        pushed_at=row["pushed_at"],
        updated_at=row["updated_at"],
        starred_at=row["starred_at"],
        summary_zh=effective_summary_zh,
        keywords=effective_keywords,
        search_score=search_score,
        match_reasons=match_reasons,
        readme_last_attempt_at=row["readme_last_attempt_at"] if include_internal else None,
        readme_failures=(row["readme_failures"] or 0) if include_internal else None,
        readme_empty=bool(row["readme_empty"] or 0) if include_internal else None,
    )
    return repo


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


def _escape_like(value: str) -> str:
    """Escape special characters for SQL LIKE queries."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_sort_timestamp(value: Any) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _interest_boost(row: Dict[str, Any], topic_scores: Dict[str, float]) -> float:
    if not topic_scores:
        return 0.0
    candidates: List[str] = []
    for key in ("category", "subcategory"):
        token = str(row.get(key) or "").strip().lower()
        if token:
            candidates.append(token)
    for field in ("ai_tags", "override_tags", "ai_keywords", "override_keywords"):
        for token in _load_json_list(row.get(field)):
            normalized = str(token).strip().lower()
            if normalized:
                candidates.append(normalized)
    total = 0.0
    for token in candidates:
        total += float(topic_scores.get(token, 0.0))
    return min(3.0, total * 0.12)


async def list_repos(
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[List[str]] = None,
    tag_mode: str = "or",
    sort: str = "stars",
    topic_scores: Optional[Dict[str, float]] = None,
    star_user: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[int, List[RepoBase]]:
    clauses = []
    params: List[Any] = []

    if q:
        fts_query = _build_fts_query(q) if _fts_enabled else None
        if fts_query:
            clauses.append("id IN (SELECT rowid FROM repos_fts WHERE repos_fts MATCH ?)")
            params.append(fts_query)
        else:
            escaped_q = _escape_like(q)
            like = f"%{escaped_q}%"
            clauses.append(
                "("
                "name LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
                "OR topics LIKE ? ESCAPE '\\' OR ai_tags LIKE ? ESCAPE '\\' OR override_tags LIKE ? ESCAPE '\\' "
                "OR ai_tag_ids LIKE ? ESCAPE '\\' OR override_tag_ids LIKE ? ESCAPE '\\' "
                "OR readme_summary LIKE ? ESCAPE '\\' OR star_users LIKE ? ESCAPE '\\' OR summary_zh LIKE ? ESCAPE '\\' "
                "OR override_summary_zh LIKE ? ESCAPE '\\' OR ai_keywords LIKE ? ESCAPE '\\' "
                "OR override_keywords LIKE ? ESCAPE '\\'"
                ")"
            )
            params.extend([like, like, like, like, like, like, like, like, like, like, like, like, like, like])

    if language:
        clauses.append("language = ?")
        params.append(language)

    if min_stars is not None:
        clauses.append("stargazers_count >= ?")
        params.append(min_stars)

    if category:
        clauses.append("COALESCE(NULLIF(override_category, ''), category) = ?")
        params.append(category)

    if subcategory:
        clauses.append("COALESCE(NULLIF(override_subcategory, ''), subcategory) = ?")
        params.append(subcategory)

    if tag:
        clauses.append(
            "("
            "COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids, '') LIKE ? "
            "OR COALESCE(NULLIF(override_tags, ''), ai_tags, '') LIKE ?"
            ")"
        )
        params.append(f"%\"{tag}\"%")
        params.append(f"%\"{tag}\"%")

    if tags:
        tag_clauses = []
        for t in tags:
            tag_clauses.append(
                "("
                "COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids, '') LIKE ? "
                "OR COALESCE(NULLIF(override_tags, ''), ai_tags, '') LIKE ?"
                ")"
            )
            params.append(f'%"{t}"%')
            params.append(f'%"{t}"%')
        joiner = " AND " if str(tag_mode).lower() == "and" else " OR "
        clauses.append("(" + joiner.join(tag_clauses) + ")")

    if star_user:
        clauses.append("star_users LIKE ?")
        params.append(f"%\"{star_user}\"%")

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    select_sql = f"""
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
        {where_sql}
    """
    normalized_sort = str(sort or "stars").strip().lower()
    if normalized_sort not in ("relevance", "stars", "updated"):
        normalized_sort = "stars"

    async with get_connection() as conn:
        total = (await (await conn.execute(
            f"SELECT COUNT(*) FROM repos {where_sql}", params
        )).fetchone())[0]
        if normalized_sort == "updated":
            rows = await (await conn.execute(
                f"""
                {select_sql}
                ORDER BY updated_at DESC, stargazers_count DESC, full_name ASC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )).fetchall()
            return total, [_row_to_repo(row) for row in rows]

        if normalized_sort != "relevance" or not q:
            rows = await (await conn.execute(
                f"""
                {select_sql}
                ORDER BY stargazers_count DESC, full_name ASC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )).fetchall()
            return total, [_row_to_repo(row) for row in rows]

        # Relevance re-ranking with explainable match reasons.
        rows = await (await conn.execute(
            f"""
            {select_sql}
            ORDER BY stargazers_count DESC, full_name ASC
            """,
            params,
        )).fetchall()

    ranked_rows: List[Dict[str, Any]] = []
    for row in rows:
        row_dict: Dict[str, Any] = dict(row)
        score, reasons = rank_repo_matches(row_dict, q or "")
        personalization = _interest_boost(row_dict, topic_scores or {})
        if personalization > 0:
            score += personalization
            reasons.append("interest_profile")
        row_dict["search_score"] = score
        row_dict["match_reasons"] = json.dumps(reasons, ensure_ascii=False)
        ranked_rows.append(row_dict)

    ranked_rows.sort(
        key=lambda item: (
            -float(item.get("search_score") or 0.0),
            -int(item.get("stargazers_count") or 0),
            -(math.floor(_parse_sort_timestamp(item.get("updated_at")))),
            str(item.get("full_name") or ""),
        )
    )
    paged_rows = ranked_rows[offset : offset + limit]
    return total, [_row_to_repo(row) for row in paged_rows]


async def iter_repos_for_export(
    language: Optional[str] = None,
    tags: Optional[List[str]] = None,
    batch_size: int = 500,
):
    """Async generator that yields repos in batches for memory-efficient export."""
    clauses = []
    params: List[Any] = []

    if language:
        clauses.append("language = ?")
        params.append(language)

    if tags:
        tag_clauses = []
        for t in tags:
            tag_clauses.append(
                "("
                "COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids, '') LIKE ? "
                "OR COALESCE(NULLIF(override_tags, ''), ai_tags, '') LIKE ?"
                ")"
            )
            params.append(f'%"{t}"%')
            params.append(f'%"{t}"%')
        clauses.append("(" + " OR ".join(tag_clauses) + ")")

    # Use keyset pagination to avoid expensive large OFFSET scans.
    # Keep ordering identical to list_repos/export consumers:
    # ORDER BY stargazers_count DESC, full_name ASC.
    cursor_stars: Optional[int] = None
    cursor_full_name: Optional[str] = None

    while True:
        page_clauses = list(clauses)
        page_params = list(params)

        if cursor_full_name is not None and cursor_stars is not None:
            page_clauses.append(
                "("
                "COALESCE(stargazers_count, -1) < ? "
                "OR (COALESCE(stargazers_count, -1) = ? AND full_name > ?)"
                ")"
            )
            page_params.extend([cursor_stars, cursor_stars, cursor_full_name])

        page_where_sql = ""
        if page_clauses:
            page_where_sql = "WHERE " + " AND ".join(page_clauses)

        async with get_connection() as conn:
            rows = await (await conn.execute(
                f"""
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
                {page_where_sql}
                ORDER BY stargazers_count DESC, full_name ASC
                LIMIT ?
                """,
                page_params + [batch_size],
            )).fetchall()

        if not rows:
            break

        for row in rows:
            yield _row_to_repo(row)

        if len(rows) < batch_size:
            break

        last = rows[-1]
        cursor_stars = int(last["stargazers_count"] or -1)
        cursor_full_name = str(last["full_name"])


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
async def update_override(full_name: str, updates: Dict[str, Any]) -> bool:
    if not updates:
        return False

    mapping = {
        "category": "override_category",
        "subcategory": "override_subcategory",
        "tags": "override_tags",
        "tag_ids": "override_tag_ids",
        "note": "override_note",
    }
    sets = []
    params: List[Any] = []

    for key, value in updates.items():
        column = mapping.get(key)
        if not column:
            continue
        if key in ("tags", "tag_ids"):
            params.append(json.dumps(value, ensure_ascii=False) if value is not None else None)
        else:
            params.append(value)
        sets.append(f"{column} = ?")

    if not sets:
        return False

    params.append(full_name)
    async with get_connection() as conn:
        before = await (await conn.execute(
            """
            SELECT
                COALESCE(NULLIF(override_category, ''), category) AS category,
                COALESCE(NULLIF(override_subcategory, ''), subcategory) AS subcategory,
                COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids) AS tag_ids
            FROM repos
            WHERE full_name = ?
            """,
            (full_name,),
        )).fetchone()
        cur = await conn.execute(
            f"UPDATE repos SET {', '.join(sets)} WHERE full_name = ?",
            params,
        )
        if cur.rowcount > 0:
            timestamp = datetime.now(timezone.utc).isoformat()
            row = await (await conn.execute(
                """
                SELECT
                    override_category, override_subcategory, override_tags, override_tag_ids, override_note,
                    COALESCE(NULLIF(override_category, ''), category) AS effective_category,
                    COALESCE(NULLIF(override_subcategory, ''), subcategory) AS effective_subcategory,
                    COALESCE(NULLIF(override_tag_ids, ''), ai_tag_ids) AS effective_tag_ids
                FROM repos
                WHERE full_name = ?
                """,
                (full_name,),
            )).fetchone()
            if row:
                await conn.execute(
                    """
                    INSERT INTO override_history
                        (full_name, category, subcategory, tags, note, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        full_name,
                        row["override_category"],
                        row["override_subcategory"],
                        row["override_tags"],
                        row["override_note"],
                        timestamp,
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO training_samples (
                        user_id,
                        full_name,
                        before_category,
                        before_subcategory,
                        before_tag_ids,
                        after_category,
                        after_subcategory,
                        after_tag_ids,
                        note,
                        source,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "global",
                        full_name,
                        before["category"] if before else None,
                        before["subcategory"] if before else None,
                        before["tag_ids"] if before else None,
                        row["effective_category"],
                        row["effective_subcategory"],
                        row["effective_tag_ids"],
                        row["override_note"],
                        "manual_override",
                        timestamp,
                    ),
                )
        await conn.commit()
        return cur.rowcount > 0


@_retry_on_lock()
async def update_classification(
    full_name: str,
    category: str,
    subcategory: str,
    confidence: float,
    tags: List[str],
    tag_ids: Optional[List[str]],
    provider: str,
    model: str,
    summary_zh: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    reason: Optional[str] = None,
    decision_source: Optional[str] = None,
    rule_candidates: Optional[List[Dict[str, Any]]] = None,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    serialized_tag_ids = json.dumps(tag_ids or [], ensure_ascii=False)
    serialized_rule_candidates = (
        json.dumps(rule_candidates, ensure_ascii=False) if rule_candidates is not None else None
    )
    async with get_connection() as conn:
        if summary_zh is not None or keywords is not None:
            await conn.execute(
                """
                UPDATE repos
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?, ai_tag_ids = ?,
                    ai_provider = ?, ai_model = ?, ai_reason = ?, ai_decision_source = ?,
                    ai_rule_candidates = COALESCE(?, ai_rule_candidates),
                    ai_updated_at = ?, classify_fail_count = 0,
                    summary_zh = ?, ai_keywords = ?
                WHERE full_name = ?
                """,
                (
                    category,
                    subcategory,
                    confidence,
                    json.dumps(tags, ensure_ascii=False),
                    serialized_tag_ids,
                    provider,
                    model,
                    reason,
                    decision_source,
                    serialized_rule_candidates,
                    timestamp,
                    summary_zh,
                    json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
                    full_name,
                ),
            )
        else:
            await conn.execute(
                """
                UPDATE repos
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?, ai_tag_ids = ?,
                    ai_provider = ?, ai_model = ?, ai_reason = ?, ai_decision_source = ?,
                    ai_rule_candidates = COALESCE(?, ai_rule_candidates),
                    ai_updated_at = ?, classify_fail_count = 0
                WHERE full_name = ?
                """,
                (
                    category,
                    subcategory,
                    confidence,
                    json.dumps(tags, ensure_ascii=False),
                    serialized_tag_ids,
                    provider,
                    model,
                    reason,
                    decision_source,
                    serialized_rule_candidates,
                    timestamp,
                    full_name,
                ),
            )
        await conn.commit()


@_retry_on_lock()
async def update_classifications_bulk(items: List[Dict[str, Any]]) -> int:
    """Batch update classification results for multiple repos.

    Uses explicit transaction with rollback on error to prevent partial updates.
    """
    if not items:
        return 0
    timestamp = datetime.now(timezone.utc).isoformat()
    rows: List[Tuple[Any, ...]] = []
    for item in items:
        full_name = item.get("full_name")
        if not full_name:
            continue
        keywords = item.get("keywords")
        rule_candidates = item.get("rule_candidates")
        rows.append(
            (
                item.get("category"),
                item.get("subcategory"),
                item.get("confidence", 0.0),
                json.dumps(item.get("tags") or [], ensure_ascii=False),
                json.dumps(item.get("tag_ids") or [], ensure_ascii=False),
                item.get("provider"),
                item.get("model"),
                item.get("reason"),
                item.get("decision_source"),
                json.dumps(rule_candidates, ensure_ascii=False) if rule_candidates is not None else None,
                timestamp,
                item.get("summary_zh"),
                json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
                full_name,
            )
        )
    if not rows:
        return 0
    async with get_connection() as conn:
        try:
            await conn.executemany(
                """
                UPDATE repos
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?, ai_tag_ids = ?,
                    ai_provider = ?, ai_model = ?, ai_reason = ?, ai_decision_source = ?,
                    ai_rule_candidates = COALESCE(?, ai_rule_candidates),
                    ai_updated_at = ?, classify_fail_count = 0,
                    summary_zh = ?, ai_keywords = ?
                WHERE full_name = ?
                """,
                rows,
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return len(rows)


@_retry_on_lock()
async def record_readme_fetch(full_name: str, summary: Optional[str], success: bool) -> None:
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
    """Batch update README fetch results for multiple repos.

    Uses explicit transaction with rollback on error to prevent partial updates.
    """
    if not entries:
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    with_summary: List[Tuple[Any, ...]] = []
    empty_summary: List[Tuple[Any, ...]] = []
    failures: List[Tuple[Any, ...]] = []
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


async def select_repos_for_classification(
    limit: int, force: bool, after_full_name: Optional[str] = None
) -> List[RepoBase]:
    where = "WHERE NULLIF(override_category, '') IS NULL AND (classify_fail_count IS NULL OR classify_fail_count < 5)"
    if not force:
        where += " AND (category IS NULL OR ai_updated_at IS NULL OR ai_updated_at < pushed_at)"
    params: List[Any] = []
    order_by = """
        ORDER BY
            category IS NULL DESC,
            ai_updated_at IS NULL DESC,
            pushed_at IS NULL,
            pushed_at DESC,
            stargazers_count DESC
    """
    if force:
        order_by = "ORDER BY full_name ASC"
        if after_full_name:
            where += " AND full_name > ?"
            params.append(after_full_name)
    effective_limit = limit if limit and limit > 0 else -1
    async with get_connection() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users,
                category, subcategory, ai_confidence, ai_tags, ai_tag_ids, ai_provider, ai_model,
                ai_reason, ai_decision_source, ai_rule_candidates, ai_updated_at,
                override_category, override_subcategory, override_tags, override_tag_ids,
                override_note, readme_summary, readme_fetched_at, readme_last_attempt_at,
                readme_failures, readme_empty,
                summary_zh, ai_keywords, override_summary_zh, override_keywords
            FROM repos
            {where}
            {order_by}
            LIMIT ?
            """,
            params + [effective_limit],
        )).fetchall()
    return [_row_to_repo(row, include_internal=True) for row in rows]


async def count_unclassified_repos() -> int:
    where = (
        "WHERE NULLIF(override_category, '') IS NULL "
        "AND NULLIF(category, '') IS NULL"
    )
    async with get_connection() as conn:
        row = await (await conn.execute(f"SELECT COUNT(*) FROM repos {where}")).fetchone()
    return int(row[0] or 0)


async def count_repos_for_classification(force: bool, after_full_name: Optional[str] = None) -> int:
    where = "WHERE NULLIF(override_category, '') IS NULL AND (classify_fail_count IS NULL OR classify_fail_count < 5)"
    if not force:
        where += " AND (category IS NULL OR ai_updated_at IS NULL OR ai_updated_at < pushed_at)"
    elif after_full_name:
        where += " AND full_name > ?"
    params: List[Any] = []
    if force and after_full_name:
        params.append(after_full_name)
    async with get_connection() as conn:
        row = await (await conn.execute(
            f"SELECT COUNT(*) FROM repos {where}",
            params,
        )).fetchone()
    return int(row[0] or 0)


@_retry_on_lock()
async def increment_classify_fail_count(full_names: List[str]) -> None:
    """Increment classify_fail_count for the given repos."""
    if not full_names:
        return
    async with get_connection() as conn:
        placeholders = ",".join("?" for _ in full_names)
        await conn.execute(
            f"""
            UPDATE repos
            SET classify_fail_count = COALESCE(classify_fail_count, 0) + 1
            WHERE full_name IN ({placeholders})
            """,
            full_names,
        )
        await conn.commit()


@_retry_on_lock()
async def reset_classify_fail_count(full_names: Optional[List[str]] = None) -> int:
    """Reset classify_fail_count to 0. If full_names is None, reset all."""
    async with get_connection() as conn:
        if full_names is None:
            result = await conn.execute(
                "UPDATE repos SET classify_fail_count = 0 WHERE classify_fail_count > 0"
            )
        else:
            if not full_names:
                return 0
            placeholders = ",".join("?" for _ in full_names)
            result = await conn.execute(
                f"UPDATE repos SET classify_fail_count = 0 WHERE full_name IN ({placeholders})",
                full_names,
            )
        await conn.commit()
        return result.rowcount


async def get_failed_repos(min_fail_count: int = 5) -> List[Dict[str, Any]]:
    """Get repos that have failed classification multiple times."""
    async with get_connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT full_name, name, owner, description, language, classify_fail_count
            FROM repos
            WHERE classify_fail_count >= ?
            ORDER BY classify_fail_count DESC, full_name ASC
            """,
            (min_fail_count,),
        )).fetchall()
    return [
        {
            "full_name": row["full_name"],
            "name": row["name"],
            "owner": row["owner"],
            "description": row["description"],
            "language": row["language"],
            "classify_fail_count": row["classify_fail_count"],
        }
        for row in rows
    ]


async def list_override_history(full_name: str) -> List[Dict[str, Any]]:
    async with get_connection() as conn:
        rows = await (await conn.execute(
            """
            SELECT category, subcategory, tags, note, updated_at
            FROM override_history
            WHERE full_name = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (full_name,),
        )).fetchall()
    results: List[Dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "category": row["category"],
                "subcategory": row["subcategory"],
                "tags": _load_json_list(row["tags"]),
                "note": row["note"],
                "updated_at": row["updated_at"],
            }
        )
    return results


async def get_repo_stats() -> Dict[str, Any]:
    async with get_connection() as conn:
        total = (await (await conn.execute("SELECT COUNT(*) FROM repos")).fetchone())[0]
        unclassified = (await (await conn.execute(
            """
            SELECT COUNT(*)
            FROM repos
            WHERE NULLIF(override_category, '') IS NULL
              AND NULLIF(category, '') IS NULL
            """
        )).fetchone())[0]
        category_rows = await (await conn.execute(
            """
            SELECT
                COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized') AS name,
                COUNT(*) AS count
            FROM repos
            GROUP BY
                COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized')
            ORDER BY count DESC, name ASC
            """
        )).fetchall()
        subcategory_rows = await (await conn.execute(
            """
            SELECT
                COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized') AS category,
                COALESCE(NULLIF(override_subcategory, ''), NULLIF(subcategory, ''), 'other') AS name,
                COUNT(*) AS count
            FROM repos
            GROUP BY
                COALESCE(NULLIF(override_category, ''), NULLIF(category, ''), 'uncategorized'),
                COALESCE(NULLIF(override_subcategory, ''), NULLIF(subcategory, ''), 'other')
            ORDER BY count DESC, name ASC
            """
        )).fetchall()
        # Use json_each to aggregate tags in SQL instead of loading all into memory
        tag_rows = await (await conn.execute(
            """
            SELECT tag.value AS name, COUNT(*) AS count
            FROM repos, json_each(
                CASE
                    WHEN override_tags IS NOT NULL AND override_tags != '' AND override_tags != 'null'
                    THEN override_tags
                    ELSE COALESCE(ai_tags, '[]')
                END
            ) AS tag
            WHERE tag.value IS NOT NULL AND tag.value != ''
            GROUP BY tag.value
            ORDER BY count DESC, name ASC
            """
        )).fetchall()
        # Use json_each to aggregate users in SQL
        user_rows = await (await conn.execute(
            """
            SELECT user.value AS name, COUNT(*) AS count
            FROM repos, json_each(COALESCE(star_users, '[]')) AS user
            WHERE user.value IS NOT NULL AND user.value != ''
            GROUP BY user.value
            ORDER BY count DESC, name ASC
            """
        )).fetchall()

    category_counts = [
        {"name": row["name"], "count": int(row["count"] or 0)}
        for row in category_rows
    ]
    subcategory_counts = [
        {
            "category": row["category"],
            "name": row["name"],
            "count": int(row["count"] or 0),
        }
        for row in subcategory_rows
    ]
    tag_counts = [
        {"name": row["name"], "count": int(row["count"] or 0)}
        for row in tag_rows
    ]
    user_counts = [
        {"name": row["name"], "count": int(row["count"] or 0)}
        for row in user_rows
    ]

    return {
        "total": int(total or 0),
        "unclassified": int(unclassified or 0),
        "categories": category_counts,
        "subcategories": subcategory_counts,
        "tags": tag_counts,
        "users": user_counts,
    }


def _safe_json_dict(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


async def get_user_preferences(user_id: str = "global") -> Dict[str, Any]:
    normalized = str(user_id or "global").strip() or "global"
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT user_id, tag_mapping_json, rule_priority_json, updated_at
            FROM user_preferences
            WHERE user_id = ?
            """,
            (normalized,),
        )).fetchone()
    if not row:
        return {
            "user_id": normalized,
            "tag_mapping": {},
            "rule_priority": {},
            "updated_at": None,
        }
    return {
        "user_id": row["user_id"],
        "tag_mapping": _safe_json_dict(row["tag_mapping_json"]),
        "rule_priority": _safe_json_dict(row["rule_priority_json"]),
        "updated_at": row["updated_at"],
    }


@_retry_on_lock()
async def update_user_preferences(
    user_id: str,
    tag_mapping: Optional[Dict[str, str]] = None,
    rule_priority: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    normalized = str(user_id or "global").strip() or "global"
    current = await get_user_preferences(normalized)
    merged_tag_mapping = dict(current.get("tag_mapping") or {})
    merged_rule_priority = dict(current.get("rule_priority") or {})
    if tag_mapping is not None:
        merged_tag_mapping = {
            str(k): str(v)
            for k, v in tag_mapping.items()
            if str(k).strip() and str(v).strip()
        }
    if rule_priority is not None:
        filtered: Dict[str, int] = {}
        for key, value in rule_priority.items():
            k = str(key).strip()
            if not k:
                continue
            try:
                filtered[k] = int(value)
            except (TypeError, ValueError):
                continue
        merged_rule_priority = filtered

    timestamp = datetime.now(timezone.utc).isoformat()
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO user_preferences (user_id, tag_mapping_json, rule_priority_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                tag_mapping_json = excluded.tag_mapping_json,
                rule_priority_json = excluded.rule_priority_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized,
                json.dumps(merged_tag_mapping, ensure_ascii=False),
                json.dumps(merged_rule_priority, ensure_ascii=False),
                timestamp,
            ),
        )
        await conn.commit()

    return {
        "user_id": normalized,
        "tag_mapping": merged_tag_mapping,
        "rule_priority": merged_rule_priority,
        "updated_at": timestamp,
    }


def _extract_interest_terms(payload: Dict[str, Any]) -> Dict[str, float]:
    terms: Dict[str, float] = {}
    tags = payload.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            token = str(tag).strip().lower()
            if token:
                terms[token] = terms.get(token, 0.0) + 2.0
    category = str(payload.get("category") or "").strip().lower()
    if category:
        terms[category] = terms.get(category, 0.0) + 1.5
    subcategory = str(payload.get("subcategory") or "").strip().lower()
    if subcategory:
        terms[subcategory] = terms.get(subcategory, 0.0) + 1.2
    keywords = payload.get("keywords")
    if isinstance(keywords, list):
        for item in keywords:
            token = str(item).strip().lower()
            if token:
                terms[token] = terms.get(token, 0.0) + 1.0
    query = str(payload.get("query") or "").strip().lower()
    if query:
        for token in re.split(r"[^\w\u4e00-\u9fff]+", query):
            normalized = token.strip()
            if normalized:
                terms[normalized] = terms.get(normalized, 0.0) + 0.6
    return terms


async def _load_repo_interest_payload(conn: aiosqlite.Connection, full_name: str) -> Dict[str, Any]:
    row = await (await conn.execute(
        """
        SELECT
            COALESCE(NULLIF(override_category, ''), category) AS category,
            COALESCE(NULLIF(override_subcategory, ''), subcategory) AS subcategory,
            COALESCE(NULLIF(override_tags, ''), ai_tags) AS tags,
            COALESCE(NULLIF(override_keywords, ''), ai_keywords) AS keywords
        FROM repos
        WHERE full_name = ?
        """,
        (full_name,),
    )).fetchone()
    if not row:
        return {}
    return {
        "category": row["category"],
        "subcategory": row["subcategory"],
        "tags": _load_json_list(row["tags"]),
        "keywords": _load_json_list(row["keywords"]),
    }


@_retry_on_lock()
async def record_user_feedback_event(
    user_id: str,
    event_type: str,
    query: Optional[str] = None,
    full_name: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    normalized_user = str(user_id or "global").strip() or "global"
    normalized_event = str(event_type or "").strip().lower()
    if normalized_event not in ("search", "click"):
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_obj = dict(payload or {})
    if query and not payload_obj.get("query"):
        payload_obj["query"] = query

    async with get_connection() as conn:
        if normalized_event == "click" and full_name:
            repo_payload = await _load_repo_interest_payload(conn, full_name)
            for key, value in repo_payload.items():
                payload_obj.setdefault(key, value)

        await conn.execute(
            """
            INSERT INTO user_feedback_events (user_id, event_type, query, full_name, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_user,
                normalized_event,
                query,
                full_name,
                json.dumps(payload_obj, ensure_ascii=False),
                timestamp,
            ),
        )

        current_profile_row = await (await conn.execute(
            """
            SELECT topic_scores
            FROM user_interest_profiles
            WHERE user_id = ?
            """,
            (normalized_user,),
        )).fetchone()
        current_scores = _safe_json_dict(current_profile_row["topic_scores"]) if current_profile_row else {}
        updated_scores: Dict[str, float] = {}
        for key, value in current_scores.items():
            try:
                updated_scores[str(key)] = float(value) * 0.98
            except (TypeError, ValueError):
                continue
        for term, inc in _extract_interest_terms(payload_obj).items():
            updated_scores[term] = updated_scores.get(term, 0.0) + float(inc)
        # keep profile compact
        top_items = sorted(updated_scores.items(), key=lambda item: item[1], reverse=True)[:200]
        compact_scores = {k: round(v, 4) for k, v in top_items if v > 0}

        await conn.execute(
            """
            INSERT INTO user_interest_profiles (user_id, topic_scores, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                topic_scores = excluded.topic_scores,
                updated_at = excluded.updated_at
            """,
            (
                normalized_user,
                json.dumps(compact_scores, ensure_ascii=False),
                timestamp,
            ),
        )
        await conn.commit()


async def get_user_interest_profile(user_id: str = "global") -> Dict[str, Any]:
    normalized = str(user_id or "global").strip() or "global"
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT user_id, topic_scores, updated_at
            FROM user_interest_profiles
            WHERE user_id = ?
            """,
            (normalized,),
        )).fetchone()
    if not row:
        return {"user_id": normalized, "topic_scores": {}, "top_topics": [], "updated_at": None}
    scores = _safe_json_dict(row["topic_scores"])
    normalized_scores: Dict[str, float] = {}
    for key, value in scores.items():
        try:
            normalized_scores[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    top_topics = sorted(normalized_scores.items(), key=lambda item: item[1], reverse=True)[:20]
    return {
        "user_id": row["user_id"],
        "topic_scores": normalized_scores,
        "top_topics": [{"topic": key, "score": score} for key, score in top_topics],
        "updated_at": row["updated_at"],
    }


async def list_training_samples(
    user_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []
    if user_id:
        clauses.append("(user_id = ? OR user_id IS NULL)")
        params.append(str(user_id))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    async with get_connection() as conn:
        rows = await (await conn.execute(
            f"""
            SELECT
                id,
                user_id,
                full_name,
                before_category,
                before_subcategory,
                before_tag_ids,
                after_category,
                after_subcategory,
                after_tag_ids,
                note,
                source,
                created_at
            FROM training_samples
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params + [limit],
        )).fetchall()
    output: List[Dict[str, Any]] = []
    for row in rows:
        output.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "full_name": row["full_name"],
                "before_category": row["before_category"],
                "before_subcategory": row["before_subcategory"],
                "before_tag_ids": _load_json_list(row["before_tag_ids"]),
                "after_category": row["after_category"],
                "after_subcategory": row["after_subcategory"],
                "after_tag_ids": _load_json_list(row["after_tag_ids"]),
                "note": row["note"],
                "source": row["source"],
                "created_at": row["created_at"],
            }
        )
    return output
