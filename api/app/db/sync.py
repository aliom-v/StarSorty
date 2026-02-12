from datetime import datetime, timezone

from .helpers import _retry_on_lock
from .pool import get_connection


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
