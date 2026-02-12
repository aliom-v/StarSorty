import logging

import aiosqlite

from .helpers import _retry_on_lock
from .pool import get_connection

logger = logging.getLogger("starsorty.db")

_fts_enabled = False


def is_fts_enabled() -> bool:
    return _fts_enabled


async def _init_repos_fts(conn: aiosqlite.Connection) -> None:
    global _fts_enabled
    try:
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
    except Exception as exc:
        _fts_enabled = False
        logger.warning("SQLite FTS5 unavailable, falling back to LIKE search: %s", exc)


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
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_stargazers ON repos(stargazers_count DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_stargazers_full_name ON repos(stargazers_count DESC, full_name ASC)"
        )
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
