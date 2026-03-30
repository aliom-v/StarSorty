import logging

import aiosqlite

from .helpers import _retry_on_lock
from .pool import get_connection

logger = logging.getLogger("starsorty.db")

_fts_enabled = False
_FTS_TRIGGER_NAMES = ("repos_ai", "repos_ad", "repos_au")
_FTS_REQUIRED_SQL_FRAGMENTS = (
    "using fts5",
    "content='repos'",
    "content_rowid='id'",
    "ai_tag_ids",
    "override_tag_ids",
    "summary_zh",
    "override_summary_zh",
    "ai_keywords",
    "override_keywords",
)
_LOOKUP_TRIGGER_NAMES = (
    "repo_star_users_ai",
    "repo_star_users_au",
    "repo_star_users_ad",
    "repo_effective_tags_ai",
    "repo_effective_tags_au",
    "repo_effective_tags_ad",
)


def is_fts_enabled() -> bool:
    return _fts_enabled


async def _drop_repos_fts_objects(conn: aiosqlite.Connection) -> None:
    for trigger_name in _FTS_TRIGGER_NAMES:
        await conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    await conn.execute("DROP TABLE IF EXISTS repos_fts")


async def _create_repos_fts_objects(conn: aiosqlite.Connection) -> None:
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


async def _fts_objects_need_reset(conn: aiosqlite.Connection) -> bool:
    row = await (
        await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'repos_fts'"
        )
    ).fetchone()
    table_sql = str((row or {}).get("sql") if isinstance(row, dict) else row["sql"] if row else "")
    normalized_table_sql = table_sql.lower()
    if not normalized_table_sql:
        return True
    if any(fragment not in normalized_table_sql for fragment in _FTS_REQUIRED_SQL_FRAGMENTS):
        return True

    for trigger_name in _FTS_TRIGGER_NAMES:
        trigger_row = await (
            await conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (trigger_name,),
            )
        ).fetchone()
        trigger_sql = (
            str((trigger_row or {}).get("sql"))
            if isinstance(trigger_row, dict)
            else str(trigger_row["sql"])
            if trigger_row
            else ""
        )
        if "repos_fts" not in trigger_sql.lower():
            return True
    return False


async def _init_repos_fts(conn: aiosqlite.Connection) -> None:
    global _fts_enabled
    try:
        if await _fts_objects_need_reset(conn):
            await _drop_repos_fts_objects(conn)
            await _create_repos_fts_objects(conn)

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


async def _drop_repo_lookup_triggers(conn: aiosqlite.Connection) -> None:
    for trigger_name in _LOOKUP_TRIGGER_NAMES:
        await conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")


async def _create_repo_lookup_tables(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repo_star_users (
            repo_id INTEGER NOT NULL,
            star_user TEXT NOT NULL,
            PRIMARY KEY (repo_id, star_user),
            FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repo_effective_tags (
            repo_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            tag_id TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (repo_id, tag, tag_id),
            FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE
        )
        """
    )


async def _create_repo_lookup_triggers(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS repo_star_users_ai
        AFTER INSERT ON repos BEGIN
            DELETE FROM repo_star_users WHERE repo_id = new.id;
            INSERT INTO repo_star_users(repo_id, star_user)
            SELECT new.id, star_user.value
            FROM json_each(
                CASE
                    WHEN json_valid(COALESCE(new.star_users, '[]')) THEN COALESCE(new.star_users, '[]')
                    ELSE '[]'
                END
            ) AS star_user
            WHERE star_user.value IS NOT NULL AND star_user.value != '';
        END;
        """
    )
    await conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS repo_star_users_au
        AFTER UPDATE OF star_users ON repos BEGIN
            DELETE FROM repo_star_users WHERE repo_id = old.id;
            INSERT INTO repo_star_users(repo_id, star_user)
            SELECT new.id, star_user.value
            FROM json_each(
                CASE
                    WHEN json_valid(COALESCE(new.star_users, '[]')) THEN COALESCE(new.star_users, '[]')
                    ELSE '[]'
                END
            ) AS star_user
            WHERE star_user.value IS NOT NULL AND star_user.value != '';
        END;
        """
    )
    await conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS repo_star_users_ad
        AFTER DELETE ON repos BEGIN
            DELETE FROM repo_star_users WHERE repo_id = old.id;
        END;
        """
    )
    await conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS repo_effective_tags_ai
        AFTER INSERT ON repos BEGIN
            DELETE FROM repo_effective_tags WHERE repo_id = new.id;
            INSERT INTO repo_effective_tags(repo_id, tag, tag_id)
            SELECT
                new.id,
                tag.value,
                COALESCE(tag_id.value, '')
            FROM json_each(
                CASE
                    WHEN new.override_tags IS NOT NULL AND new.override_tags != ''
                        THEN CASE WHEN json_valid(new.override_tags) THEN new.override_tags ELSE '[]' END
                    WHEN json_valid(COALESCE(new.ai_tags, '[]'))
                        THEN COALESCE(new.ai_tags, '[]')
                    ELSE '[]'
                END
            ) AS tag
            LEFT JOIN json_each(
                CASE
                    WHEN new.override_tag_ids IS NOT NULL AND new.override_tag_ids != ''
                        THEN CASE WHEN json_valid(new.override_tag_ids) THEN new.override_tag_ids ELSE '[]' END
                    WHEN json_valid(COALESCE(new.ai_tag_ids, '[]'))
                        THEN COALESCE(new.ai_tag_ids, '[]')
                    ELSE '[]'
                END
            ) AS tag_id
                ON tag.key = tag_id.key
            WHERE tag.value IS NOT NULL AND tag.value != '';
        END;
        """
    )
    await conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS repo_effective_tags_au
        AFTER UPDATE OF ai_tags, ai_tag_ids, override_tags, override_tag_ids ON repos BEGIN
            DELETE FROM repo_effective_tags WHERE repo_id = old.id;
            INSERT INTO repo_effective_tags(repo_id, tag, tag_id)
            SELECT
                new.id,
                tag.value,
                COALESCE(tag_id.value, '')
            FROM json_each(
                CASE
                    WHEN new.override_tags IS NOT NULL AND new.override_tags != ''
                        THEN CASE WHEN json_valid(new.override_tags) THEN new.override_tags ELSE '[]' END
                    WHEN json_valid(COALESCE(new.ai_tags, '[]'))
                        THEN COALESCE(new.ai_tags, '[]')
                    ELSE '[]'
                END
            ) AS tag
            LEFT JOIN json_each(
                CASE
                    WHEN new.override_tag_ids IS NOT NULL AND new.override_tag_ids != ''
                        THEN CASE WHEN json_valid(new.override_tag_ids) THEN new.override_tag_ids ELSE '[]' END
                    WHEN json_valid(COALESCE(new.ai_tag_ids, '[]'))
                        THEN COALESCE(new.ai_tag_ids, '[]')
                    ELSE '[]'
                END
            ) AS tag_id
                ON tag.key = tag_id.key
            WHERE tag.value IS NOT NULL AND tag.value != '';
        END;
        """
    )
    await conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS repo_effective_tags_ad
        AFTER DELETE ON repos BEGIN
            DELETE FROM repo_effective_tags WHERE repo_id = old.id;
        END;
        """
    )


async def _rebuild_repo_lookup_tables(conn: aiosqlite.Connection) -> None:
    await conn.execute("DELETE FROM repo_star_users")
    await conn.execute(
        """
        INSERT INTO repo_star_users(repo_id, star_user)
        SELECT repos.id, star_user.value
        FROM repos, json_each(
            CASE
                WHEN json_valid(COALESCE(repos.star_users, '[]')) THEN COALESCE(repos.star_users, '[]')
                ELSE '[]'
            END
        ) AS star_user
        WHERE star_user.value IS NOT NULL AND star_user.value != ''
        """
    )
    await conn.execute("DELETE FROM repo_effective_tags")
    await conn.execute(
        """
        INSERT INTO repo_effective_tags(repo_id, tag, tag_id)
        SELECT
            repos.id,
            tag.value,
            COALESCE(tag_id.value, '')
        FROM repos
        JOIN json_each(
            CASE
                WHEN repos.override_tags IS NOT NULL AND repos.override_tags != ''
                    THEN CASE WHEN json_valid(repos.override_tags) THEN repos.override_tags ELSE '[]' END
                WHEN json_valid(COALESCE(repos.ai_tags, '[]'))
                    THEN COALESCE(repos.ai_tags, '[]')
                ELSE '[]'
            END
        ) AS tag
        LEFT JOIN json_each(
            CASE
                WHEN repos.override_tag_ids IS NOT NULL AND repos.override_tag_ids != ''
                    THEN CASE WHEN json_valid(repos.override_tag_ids) THEN repos.override_tag_ids ELSE '[]' END
                WHEN json_valid(COALESCE(repos.ai_tag_ids, '[]'))
                    THEN COALESCE(repos.ai_tag_ids, '[]')
                ELSE '[]'
            END
        ) AS tag_id
            ON tag.key = tag_id.key
        WHERE tag.value IS NOT NULL AND tag.value != ''
        """
    )


async def _init_repo_lookup_tables(conn: aiosqlite.Connection) -> None:
    await _create_repo_lookup_tables(conn)
    await _drop_repo_lookup_triggers(conn)
    await _create_repo_lookup_triggers(conn)

    repos_total = (await (await conn.execute("SELECT COUNT(*) FROM repos")).fetchone())[0]
    star_lookup_total = (
        await (await conn.execute("SELECT COUNT(*) FROM repo_star_users")).fetchone()
    )[0]
    expected_star_lookup_total = (
        await (
            await conn.execute(
                """
                SELECT COUNT(*)
                FROM repos, json_each(
                    CASE
                        WHEN json_valid(COALESCE(repos.star_users, '[]')) THEN COALESCE(repos.star_users, '[]')
                        ELSE '[]'
                    END
                ) AS star_user
                WHERE star_user.value IS NOT NULL AND star_user.value != ''
                """
            )
        ).fetchone()
    )[0]
    expected_tag_lookup_total = (
        await (
            await conn.execute(
                """
                SELECT COUNT(*)
                FROM repos
                JOIN json_each(
                    CASE
                        WHEN repos.override_tags IS NOT NULL AND repos.override_tags != ''
                            THEN CASE WHEN json_valid(repos.override_tags) THEN repos.override_tags ELSE '[]' END
                        WHEN json_valid(COALESCE(repos.ai_tags, '[]'))
                            THEN COALESCE(repos.ai_tags, '[]')
                        ELSE '[]'
                    END
                ) AS tag
                WHERE tag.value IS NOT NULL AND tag.value != ''
                """
            )
        ).fetchone()
    )[0]
    tag_lookup_total = (
        await (await conn.execute("SELECT COUNT(*) FROM repo_effective_tags")).fetchone()
    )[0]

    if (
        star_lookup_total != expected_star_lookup_total
        or tag_lookup_total != expected_tag_lookup_total
    ):
        logger.info(
            "Rebuilding repo lookup tables (repos=%s, stars=%s/%s, tags=%s/%s)",
            repos_total,
            star_lookup_total,
            expected_star_lookup_total,
            tag_lookup_total,
            expected_tag_lookup_total,
        )
        await _rebuild_repo_lookup_tables(conn)


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


async def _normalize_active_task_uniqueness(conn: aiosqlite.Connection) -> None:
    for task_type in ("sync", "classify"):
        rows = await (
            await conn.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE task_type = ?
                  AND status IN ('queued', 'running', 'processing')
                ORDER BY COALESCE(started_at, created_at) DESC, created_at DESC
                """,
                (task_type,),
            )
        ).fetchall()
        if len(rows) <= 1:
            continue
        keep_task_id = rows[0]["task_id"]
        stale_task_ids = [row["task_id"] for row in rows[1:]]
        placeholders = ",".join("?" for _ in stale_task_ids)
        await conn.execute(
            f"""
            UPDATE tasks
            SET status = 'failed',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                message = CASE
                    WHEN message IS NULL OR message = '' THEN 'Superseded by newer active task'
                    ELSE message
                END
            WHERE task_id IN ({placeholders})
            """,
            stale_task_ids,
        )
        logger.warning(
            "Collapsed duplicate active %s tasks, keeping %s and failing %s older tasks",
            task_type,
            keep_task_id,
            len(stale_task_ids),
        )


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
            CREATE TABLE IF NOT EXISTS stats_snapshots (
                snapshot_key TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state (
                state_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_metrics (
                metric_key TEXT PRIMARY KEY,
                metric_value INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                namespace_version INTEGER NOT NULL,
                payload TEXT NOT NULL,
                expires_at REAL NOT NULL,
                updated_at TEXT NOT NULL
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
            CREATE TABLE IF NOT EXISTS admin_sessions (
                session_token_hash TEXT PRIMARY KEY,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
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
        await _normalize_active_task_uniqueness(conn)
        await _init_repos_fts(conn)
        await _init_repo_lookup_tables(conn)
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
            "CREATE INDEX IF NOT EXISTS idx_repos_subcategory ON repos(subcategory)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repos_override_subcategory ON repos(override_subcategory)"
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
            "CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires_at ON admin_sessions(expires_at)"
        )
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_active_sync_unique
            ON tasks(task_type)
            WHERE task_type = 'sync' AND status IN ('queued', 'running', 'processing')
            """
        )
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_active_classify_unique
            ON tasks(task_type)
            WHERE task_type = 'classify' AND status IN ('queued', 'running', 'processing')
            """
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
            "CREATE INDEX IF NOT EXISTS idx_repos_updated_stargazers_full_name ON repos(updated_at DESC, stargazers_count DESC, full_name ASC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repo_star_users_user_repo ON repo_star_users(star_user, repo_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repo_effective_tags_tag_repo ON repo_effective_tags(tag, repo_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repo_effective_tags_tag_id_repo ON repo_effective_tags(tag_id, repo_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_entries_namespace_expires_at ON cache_entries(namespace, expires_at)"
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
