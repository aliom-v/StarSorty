import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .config import get_settings


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


@contextmanager
def get_connection():
    settings = get_settings()
    db_path = _sqlite_path(settings.database_url)
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_at TEXT,
                last_result TEXT,
                last_message TEXT
            )
            """
        )
        conn.execute(
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
                readme_fetched_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_columns(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repos(full_name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_language ON repos(language)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_category ON repos(category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_override_category ON repos(override_category)"
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO sync_status (id, last_sync_at, last_result, last_message)
            VALUES (1, NULL, NULL, NULL)
            """
        )
        conn.commit()


def get_sync_status() -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_sync_at, last_result, last_message FROM sync_status WHERE id = 1"
        ).fetchone()
        if row is None:
            return {"last_sync_at": None, "last_result": None, "last_message": None}
        return {
            "last_sync_at": row[0],
            "last_result": row[1],
            "last_message": row[2],
        }


def update_sync_status(result: str, message: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sync_status
            SET last_sync_at = ?, last_result = ?, last_message = ?
            WHERE id = 1
            """,
            (timestamp, result, message),
        )
        conn.commit()
    return timestamp


def _ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(repos)").fetchall()
    }
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
    ]
    for name, ddl in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE repos ADD COLUMN {ddl}")


def upsert_repos(repos: List[Dict[str, Any]]) -> int:
    if not repos:
        return 0
    existing_users = _load_star_users(repos)

    for repo in repos:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        current_users = set(existing_users.get(full_name, []))
        new_users = set(repo.get("star_users") or [])
        merged = sorted(current_users | new_users)
        repo["star_users"] = merged
    with get_connection() as conn:
        conn.executemany(
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
        conn.commit()
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


def _load_star_users(repos: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    names = [repo.get("full_name") for repo in repos if repo.get("full_name")]
    if not names:
        return {}
    placeholders = ",".join("?" for _ in names)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT full_name, star_users FROM repos WHERE full_name IN ({placeholders})",
            names,
        ).fetchall()
    existing: Dict[str, List[str]] = {}
    for row in rows:
        existing[row["full_name"]] = _load_json_list(row["star_users"])
    return existing


def _row_to_repo(row: sqlite3.Row) -> Dict[str, Any]:
    topics = _load_json_list(row["topics"])
    star_users = _load_json_list(row["star_users"])
    ai_tags = _load_json_list(row["ai_tags"])
    override_tags = _load_json_list(row["override_tags"])
    effective_category = row["override_category"] or row["category"]
    effective_subcategory = row["override_subcategory"] or row["subcategory"]
    effective_tags = override_tags or ai_tags
    return {
        "full_name": row["full_name"],
        "name": row["name"],
        "owner": row["owner"],
        "html_url": row["html_url"],
        "description": row["description"],
        "language": row["language"],
        "stargazers_count": row["stargazers_count"],
        "forks_count": row["forks_count"],
        "topics": topics,
        "star_users": star_users,
        "category": effective_category,
        "subcategory": effective_subcategory,
        "tags": effective_tags,
        "ai_category": row["category"],
        "ai_subcategory": row["subcategory"],
        "ai_confidence": row["ai_confidence"],
        "ai_tags": ai_tags,
        "ai_provider": row["ai_provider"],
        "ai_model": row["ai_model"],
        "ai_updated_at": row["ai_updated_at"],
        "override_category": row["override_category"],
        "override_subcategory": row["override_subcategory"],
        "override_tags": override_tags,
        "override_note": row["override_note"],
        "readme_summary": row["readme_summary"],
        "readme_fetched_at": row["readme_fetched_at"],
        "pushed_at": row["pushed_at"],
        "updated_at": row["updated_at"],
        "starred_at": row["starred_at"],
    }


def list_repos(
    q: Optional[str] = None,
    language: Optional[str] = None,
    min_stars: Optional[int] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    star_user: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[int, List[Dict[str, Any]]]:
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
        clauses.append(
            "COALESCE(override_category, category) = ?"
        )
        params.append(category)

    if tag:
        clauses.append(
            "COALESCE(override_tags, ai_tags) LIKE ?"
        )
        params.append(f"%\"{tag}\"%")

    if star_user:
        clauses.append("star_users LIKE ?")
        params.append(f"%\"{star_user}\"%")

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    with get_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM repos {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
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
        ).fetchall()
    return total, [_row_to_repo(row) for row in rows]


def get_repo(full_name: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
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
        ).fetchone()
        if not row:
            return None
    return _row_to_repo(row)


def update_override(full_name: str, updates: Dict[str, Any]) -> bool:
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
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE repos SET {', '.join(sets)} WHERE full_name = ?",
            params,
        )
        conn.commit()
        return cur.rowcount > 0


def update_classification(
    full_name: str,
    category: str,
    subcategory: str,
    confidence: float,
    tags: List[str],
    provider: str,
    model: str,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
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
        conn.commit()


def update_readme_summary(full_name: str, summary: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE repos
            SET readme_summary = ?, readme_fetched_at = ?
            WHERE full_name = ?
            """,
            (summary, timestamp, full_name),
        )
        conn.commit()


def select_repos_for_classification(limit: int, force: bool) -> List[Dict[str, Any]]:
    where = "WHERE override_category IS NULL"
    if not force:
        where += " AND (category IS NULL OR ai_updated_at IS NULL OR ai_updated_at < pushed_at)"
    effective_limit = limit if limit and limit > 0 else -1
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                full_name, name, owner, html_url, description, language,
                stargazers_count, forks_count, topics, pushed_at, updated_at, starred_at,
                star_users,
                category, subcategory, ai_confidence, ai_tags, ai_provider, ai_model,
                ai_updated_at, override_category, override_subcategory, override_tags,
                override_note, readme_summary, readme_fetched_at
            FROM repos
            {where}
            ORDER BY
                category IS NULL DESC,
                ai_updated_at IS NULL DESC,
                pushed_at IS NULL,
                pushed_at DESC,
                stargazers_count DESC
            LIMIT ?
            """,
            (effective_limit,),
        ).fetchall()
    return [_row_to_repo(row) for row in rows]


def count_unclassified_repos() -> int:
    where = "WHERE override_category IS NULL AND category IS NULL"
    with get_connection() as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM repos {where}").fetchone()
    return int(row[0] or 0)
