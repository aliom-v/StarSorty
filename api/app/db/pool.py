import asyncio
import logging
import os
from contextlib import asynccontextmanager

import aiosqlite

from ..config import get_settings
from .helpers import _env_int, _sqlite_path, _ensure_parent_dir

logger = logging.getLogger("starsorty.db")

_pool: "SQLitePool | None" = None

SQLITE_JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "WAL").upper()
SQLITE_SYNCHRONOUS = os.getenv("SQLITE_SYNCHRONOUS", "NORMAL").upper()
SQLITE_BUSY_TIMEOUT = _env_int("SQLITE_BUSY_TIMEOUT", 5000, minimum=1)


async def _configure_connection(conn: aiosqlite.Connection) -> None:
    try:
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


async def init_db_pool(pool_size: int | None = None) -> None:
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
