import json
import logging
from datetime import datetime, timezone
from typing import Any

from .db.pool import get_connection

logger = logging.getLogger("starsorty.runtime")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def load_runtime_state(state_key: str) -> dict[str, Any] | None:
    async with get_connection() as conn:
        row = await (
            await conn.execute(
                """
                SELECT payload
                FROM runtime_state
                WHERE state_key = ?
                """,
                (state_key,),
            )
        ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload"])
    except Exception:
        logger.warning("Failed to parse runtime_state payload for %s", state_key)
        return None
    return payload if isinstance(payload, dict) else None


async def store_runtime_state(state_key: str, payload: dict[str, Any]) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO runtime_state (state_key, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                state_key,
                json.dumps(payload, ensure_ascii=False),
                _now_iso(),
            ),
        )
        await conn.commit()


async def add_runtime_metrics(delta: dict[str, int]) -> None:
    normalized = {
        key: _to_int(value)
        for key, value in delta.items()
        if _to_int(value) != 0
    }
    if not normalized:
        return
    timestamp = _now_iso()
    async with get_connection() as conn:
        for key, value in normalized.items():
            await conn.execute(
                """
                INSERT INTO runtime_metrics (metric_key, metric_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(metric_key) DO UPDATE SET
                    metric_value = runtime_metrics.metric_value + excluded.metric_value,
                    updated_at = excluded.updated_at
                """,
                (key, value, timestamp),
            )
        await conn.commit()


async def get_runtime_metrics() -> dict[str, int]:
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT metric_key, metric_value
                FROM runtime_metrics
                """
            )
        ).fetchall()
    return {
        str(row["metric_key"]): _to_int(row["metric_value"])
        for row in rows
        if row["metric_key"]
    }
