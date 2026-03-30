import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

from .settings_meta import get_setting_spec, OVERRIDABLE_SETTING_KEYS, coerce_setting_value

_settings_store_revision = 0
_settings_store_revision_lock = threading.Lock()


def get_settings_store_revision() -> int:
    with _settings_store_revision_lock:
        return _settings_store_revision


def _bump_settings_store_revision() -> int:
    global _settings_store_revision
    with _settings_store_revision_lock:
        _settings_store_revision += 1
        return _settings_store_revision


def _sqlite_path(database_url: str) -> str:
    if database_url.startswith("sqlite:////"):
        return "/" + database_url[len("sqlite:////") :]
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///") :]
    raise ValueError("Only sqlite is supported in the settings store")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _get_db_path() -> str:
    database_url = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
    return _sqlite_path(database_url)


def read_settings(keys: Iterable[str] | None = None) -> Dict[str, Any]:
    db_path = _get_db_path()
    if not Path(db_path).exists():
        return {}
    key_list = [str(key).strip().upper() for key in (keys or OVERRIDABLE_SETTING_KEYS) if str(key).strip()]
    if not key_list:
        return {}
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in key_list)
        rows = conn.execute(
            f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
            key_list,
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        if conn is not None:
            conn.close()

    settings: Dict[str, Any] = {}
    for row in rows:
        raw = row["value"]
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        spec = get_setting_spec(row["key"])
        settings[row["key"]] = (
            coerce_setting_value(spec, parsed) if spec is not None else parsed
        )
    return settings


def write_settings(values: Dict[str, Any]) -> None:
    if not values:
        return
    db_path = _get_db_path()
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    wrote_any = False
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for key, value in values.items():
            normalized_key = str(key or "").strip().upper()
            spec = get_setting_spec(normalized_key)
            if spec is None or spec.env_only:
                continue
            encoded = json.dumps(coerce_setting_value(spec, value), ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (normalized_key, encoded),
            )
            wrote_any = True
        conn.commit()
    finally:
        conn.close()
    if wrote_any:
        _bump_settings_store_revision()
