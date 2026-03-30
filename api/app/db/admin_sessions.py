import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from .helpers import _retry_on_lock
from .pool import get_connection


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hash_session_token(session_token: str) -> str:
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()


def generate_admin_session_tokens() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(24)


def build_admin_session_expiry(ttl_seconds: int) -> datetime:
    return _now_utc() + timedelta(seconds=max(1, ttl_seconds))


def _row_to_session(row) -> Dict[str, Any]:
    return {
        "created_at": row["created_at"],
        "last_seen_at": row["last_seen_at"],
        "expires_at": row["expires_at"],
        "csrf_token": row["csrf_token"],
    }


@_retry_on_lock()
async def purge_expired_admin_sessions(now: datetime | None = None) -> int:
    current = (now or _now_utc()).isoformat()
    async with get_connection() as conn:
        cursor = await conn.execute(
            "DELETE FROM admin_sessions WHERE expires_at <= ?",
            (current,),
        )
        await conn.commit()
        return int(cursor.rowcount or 0)


@_retry_on_lock()
async def create_admin_session(
    session_token: str,
    csrf_token: str,
    *,
    expires_at: datetime,
) -> None:
    timestamp = _now_utc().isoformat()
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO admin_sessions (
                session_token_hash,
                csrf_token,
                created_at,
                last_seen_at,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _hash_session_token(session_token),
                csrf_token,
                timestamp,
                timestamp,
                expires_at.isoformat(),
            ),
        )
        await conn.commit()


@_retry_on_lock()
async def get_admin_session(session_token: str) -> Dict[str, Any] | None:
    now = _now_utc()
    async with get_connection() as conn:
        row = await (
            await conn.execute(
                """
                SELECT
                    csrf_token,
                    created_at,
                    last_seen_at,
                    expires_at
                FROM admin_sessions
                WHERE session_token_hash = ?
                """,
                (_hash_session_token(session_token),),
            )
        ).fetchone()
        if not row:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= now:
            await conn.execute(
                "DELETE FROM admin_sessions WHERE session_token_hash = ?",
                (_hash_session_token(session_token),),
            )
            await conn.commit()
            return None
        await conn.execute(
            """
            UPDATE admin_sessions
            SET last_seen_at = ?
            WHERE session_token_hash = ?
            """,
            (now.isoformat(), _hash_session_token(session_token)),
        )
        await conn.commit()
    session = _row_to_session(row)
    session["last_seen_at"] = now.isoformat()
    return session


@_retry_on_lock()
async def delete_admin_session(session_token: str) -> bool:
    async with get_connection() as conn:
        cursor = await conn.execute(
            "DELETE FROM admin_sessions WHERE session_token_hash = ?",
            (_hash_session_token(session_token),),
        )
        await conn.commit()
        return bool(cursor.rowcount)
