import asyncio
import functools
import json
import logging
import os
import random
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from .config import get_settings
from .models import RepoBase

logger = logging.getLogger("starsorty.db")
_pool: "SQLitePool | None" = None


def _retry_on_lock(
    max_attempts: int = 5,
    base_delay: float = 0.05,
    max_delay: float = 0.5,
) -> callable:
    def decorator(func: callable) -> callable:
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


# SQLite configuration from environment
SQLITE_JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "WAL").upper()
SQLITE_SYNCHRONOUS = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL").upper()
SQLITE_BUSY_TIMEOUT = int(os.getenv("SQLITE_BUSY_TIMEOUT", "5000"))


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
        pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
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
                ai_provider TEXT,
                ai_model TEXT,
                ai_updated_at TEXT,
                override_category TEXT,
                override_subcategory TEXT,
                override_tags TEXT,
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
        await _ensure_columns(conn)
        await _ensure_task_columns(conn)
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
        # Index for force mode cursor-based pagination
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repos(full_name)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_override_history_full_name ON override_history(full_name)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_updated_at ON tasks(status, updated_at)"
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
    if not fields:
        return
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
        ("ai_provider", "ai_provider TEXT"),
        ("ai_model", "ai_model TEXT"),
        ("ai_updated_at", "ai_updated_at TEXT"),
        ("override_category", "override_category TEXT"),
        ("override_subcategory", "override_subcategory TEXT"),
        ("override_tags", "override_tags TEXT"),
        ("override_note", "override_note TEXT"),
        ("readme_summary", "readme_summary TEXT"),
        ("readme_fetched_at", "readme_fetched_at TEXT"),
        ("readme_last_attempt_at", "readme_last_attempt_at TEXT"),
        ("readme_failures", "readme_failures INTEGER"),
        ("readme_empty", "readme_empty INTEGER"),
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
    override_tags = _load_json_list_optional(row["override_tags"])
    effective_category = row["override_category"] or row["category"]
    effective_subcategory = row["override_subcategory"] or row["subcategory"]
    effective_tags = ai_tags if override_tags is None else override_tags
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
        ai_category=row["category"],
        ai_subcategory=row["subcategory"],
        ai_confidence=row["ai_confidence"],
        ai_tags=ai_tags,
        ai_provider=row["ai_provider"],
        ai_model=row["ai_model"],
        ai_updated_at=row["ai_updated_at"],
        override_category=row["override_category"],
        override_subcategory=row["override_subcategory"],
        override_tags=override_tags or [],
        override_note=row["override_note"],
        readme_summary=row["readme_summary"],
        readme_fetched_at=row["readme_fetched_at"],
        pushed_at=row["pushed_at"],
        updated_at=row["updated_at"],
        starred_at=row["starred_at"],
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


async def list_repos(
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tag: Optional[str] = None,
    star_user: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[int, List[RepoBase]]:
    clauses = []
    params: List[Any] = []

    if q:
        like = f"%{q}%"
        clauses.append(
            "("
            "name LIKE ? OR full_name LIKE ? OR description LIKE ? "
            "OR topics LIKE ? OR ai_tags LIKE ? OR override_tags LIKE ? "
            "OR star_users LIKE ?"
            ")"
        )
        params.extend([like, like, like, like, like, like, like])

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
        clauses.append("COALESCE(NULLIF(override_tags, ''), ai_tags) LIKE ?")
        params.append(f"%\"{tag}\"%")

    if star_user:
        clauses.append("star_users LIKE ?")
        params.append(f"%\"{star_user}\"%")

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    async with get_connection() as conn:
        total = (await (await conn.execute(
            f"SELECT COUNT(*) FROM repos {where_sql}", params
        )).fetchone())[0]
        rows = await (await conn.execute(
            f"""
            SELECT
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users,
                category, subcategory, ai_confidence, ai_tags, ai_provider, ai_model,
                ai_updated_at, override_category, override_subcategory, override_tags,
                override_note, readme_summary, readme_fetched_at
            FROM repos
            {where_sql}
            ORDER BY stargazers_count DESC, full_name ASC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )).fetchall()
    return total, [_row_to_repo(row) for row in rows]


async def get_repo(full_name: str) -> Optional[RepoBase]:
    async with get_connection() as conn:
        row = await (await conn.execute(
            """
            SELECT
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users,
                category, subcategory, ai_confidence, ai_tags, ai_provider, ai_model,
                ai_updated_at, override_category, override_subcategory, override_tags,
                override_note, readme_summary, readme_fetched_at
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
        "note": "override_note",
    }
    sets = []
    params: List[Any] = []

    for key, value in updates.items():
        column = mapping.get(key)
        if not column:
            continue
        if key == "tags":
            params.append(json.dumps(value) if value is not None else None)
        else:
            params.append(value)
        sets.append(f"{column} = ?")

    if not sets:
        return False

    params.append(full_name)
    async with get_connection() as conn:
        cur = await conn.execute(
            f"UPDATE repos SET {', '.join(sets)} WHERE full_name = ?",
            params,
        )
        if cur.rowcount > 0:
            timestamp = datetime.now(timezone.utc).isoformat()
            row = await (await conn.execute(
                """
                SELECT override_category, override_subcategory, override_tags, override_note
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
        await conn.commit()
        return cur.rowcount > 0


@_retry_on_lock()
async def update_classification(
    full_name: str,
    category: str,
    subcategory: str,
    confidence: float,
    tags: List[str],
    provider: str,
    model: str,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE repos
            SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?,
                ai_provider = ?, ai_model = ?, ai_updated_at = ?
            WHERE full_name = ?
            """,
            (
                category,
                subcategory,
                confidence,
                json.dumps(tags),
                provider,
                model,
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
        rows.append(
            (
                item.get("category"),
                item.get("subcategory"),
                item.get("confidence", 0.0),
                json.dumps(item.get("tags") or []),
                item.get("provider"),
                item.get("model"),
                timestamp,
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
                SET category = ?, subcategory = ?, ai_confidence = ?, ai_tags = ?,
                    ai_provider = ?, ai_model = ?, ai_updated_at = ?
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
                    SET readme_fetched_at = ?, readme_last_attempt_at = ?,
                        readme_failures = 0, readme_empty = 1
                    WHERE full_name = ?
                      AND (readme_summary IS NULL OR readme_summary = '')
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
                    SET readme_fetched_at = ?, readme_last_attempt_at = ?,
                        readme_failures = 0, readme_empty = 1
                    WHERE full_name = ?
                      AND (readme_summary IS NULL OR readme_summary = '')
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
    where = "WHERE NULLIF(override_category, '') IS NULL"
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
                category, subcategory, ai_confidence, ai_tags, ai_provider, ai_model,
                ai_updated_at, override_category, override_subcategory, override_tags,
                override_note, readme_summary, readme_fetched_at, readme_last_attempt_at,
                readme_failures, readme_empty
            FROM repos
            {where}
            {order_by}
            LIMIT ?
            """,
            params + [effective_limit],
        )).fetchall()
    return [_row_to_repo(row, include_internal=True) for row in rows]


async def count_unclassified_repos() -> int:
    where = "WHERE NULLIF(override_category, '') IS NULL AND category IS NULL"
    async with get_connection() as conn:
        row = await (await conn.execute(f"SELECT COUNT(*) FROM repos {where}")).fetchone()
    return int(row[0] or 0)


async def count_repos_for_classification(force: bool, after_full_name: Optional[str] = None) -> int:
    where = "WHERE NULLIF(override_category, '') IS NULL"
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
            "SELECT COUNT(*) FROM repos WHERE override_category IS NULL AND category IS NULL"
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
        tag_rows = await (await conn.execute(
            "SELECT override_tags, ai_tags FROM repos"
        )).fetchall()
        user_rows = await (await conn.execute("SELECT star_users FROM repos")).fetchall()

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

    tag_map: Dict[str, int] = {}
    for row in tag_rows:
        override_tags = _load_json_list_optional(row["override_tags"])
        ai_tags = _load_json_list(row["ai_tags"])
        effective_tags = ai_tags if override_tags is None else override_tags
        for tag in effective_tags:
            tag_map[tag] = tag_map.get(tag, 0) + 1
    tag_counts = sorted(
        ({"name": name, "count": count} for name, count in tag_map.items()),
        key=lambda item: (-item["count"], item["name"]),
    )

    user_map: Dict[str, int] = {}
    for row in user_rows:
        users = _load_json_list(row["star_users"])
        for user in users:
            user_map[user] = user_map.get(user, 0) + 1
    user_counts = sorted(
        ({"name": name, "count": count} for name, count in user_map.items()),
        key=lambda item: (-item["count"], item["name"]),
    )

    return {
        "total": int(total or 0),
        "unclassified": int(unclassified or 0),
        "categories": category_counts,
        "subcategories": subcategory_counts,
        "tags": tag_counts,
        "users": user_counts,
    }
