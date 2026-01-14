import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict


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


def read_settings() -> Dict[str, Any]:
    db_path = _get_db_path()
    if not Path(db_path).exists():
        return {}
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    settings: Dict[str, Any] = {}
    for row in rows:
        raw = row["value"]
        try:
            settings[row["key"]] = json.loads(raw)
        except Exception:
            settings[row["key"]] = raw
    return settings


def write_settings(values: Dict[str, Any]) -> None:
    if not values:
        return
    db_path = _get_db_path()
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
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
            encoded = json.dumps(value)
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, encoded),
            )
        conn.commit()
    finally:
        conn.close()
