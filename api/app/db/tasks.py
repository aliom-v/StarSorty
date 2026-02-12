import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .helpers import _load_json_object, _retry_on_lock
from .pool import get_connection


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
