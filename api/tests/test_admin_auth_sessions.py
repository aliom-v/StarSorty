import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.app import deps as deps_mod
from api.app.db import admin_sessions as admin_sessions_db
from api.app.db import schema as schema_db
from api.app.routes import health as health_routes


def _run(coro):
    return asyncio.run(coro)


def _build_get_connection(db_path: Path):
    @asynccontextmanager
    async def _get_connection():
        conn = await aiosqlite.connect(db_path, timeout=30)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    return _get_connection


def _sqlite_url(path: Path) -> str:
    return f"sqlite:////{str(path).lstrip('/')}"


def test_admin_session_cookie_flow_requires_csrf_for_writes(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "admin-auth.db"
    get_connection = _build_get_connection(db_path)

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(admin_sessions_db, "get_connection", get_connection)
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(health_routes.limiter, "enabled", False)

    _run(schema_db.init_db())

    app = FastAPI()
    app.state.limiter = health_routes.limiter
    app.include_router(health_routes.router)

    @app.get("/protected", dependencies=[Depends(deps_mod.require_admin)])
    async def protected_get():
        return {"ok": True}

    @app.post("/protected", dependencies=[Depends(deps_mod.require_admin)])
    async def protected_post():
        return {"ok": True}

    with TestClient(app) as client:
        bad_login = client.post("/auth/session", json={"password": "wrong"})
        assert bad_login.status_code == 401

        login = client.post("/auth/session", json={"password": "secret"})
        assert login.status_code == 200
        assert login.json() == {"ok": True, "auth_mode": "session"}

        set_cookie_headers = login.headers.get_list("set-cookie")
        assert any(
            "starsorty_admin_session=" in value and "HttpOnly" in value
            for value in set_cookie_headers
        )
        assert any(
            "starsorty_admin_csrf=" in value and "HttpOnly" not in value
            for value in set_cookie_headers
        )

        assert client.get("/auth/check").status_code == 200
        assert client.get("/auth/check", headers={"X-Admin-Token": "secret"}).status_code == 200
        assert client.get("/protected").status_code == 200
        assert client.post("/protected").status_code == 401

        csrf_token = client.cookies.get("starsorty_admin_csrf")
        assert csrf_token

        protected_post = client.post(
            "/protected",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert protected_post.status_code == 200

        health_payload = client.get("/health").json()
        assert health_payload == {
            "status": "ok",
            "security": {
                "runtime_env": "development",
                "production_mode": False,
                "admin_token_configured": True,
            },
        }

        logout = client.delete(
            "/auth/session",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logout.status_code == 200
        assert logout.json() == {"ok": True, "auth_mode": "logged_out"}

        assert client.get("/auth/check").status_code == 401


def test_admin_session_cookies_are_secure_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "admin-auth-prod.db"
    get_connection = _build_get_connection(db_path)

    monkeypatch.setattr(schema_db, "get_connection", get_connection)
    monkeypatch.setattr(admin_sessions_db, "get_connection", get_connection)
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(health_routes.limiter, "enabled", False)

    _run(schema_db.init_db())

    app = FastAPI()
    app.state.limiter = health_routes.limiter
    app.include_router(health_routes.router)

    with TestClient(app) as client:
        login = client.post("/auth/session", json={"password": "secret"})
        assert login.status_code == 200

        set_cookie_headers = login.headers.get_list("set-cookie")
        assert any(
            "starsorty_admin_session=" in value and "HttpOnly" in value and "Secure" in value
            for value in set_cookie_headers
        )
        assert any(
            "starsorty_admin_csrf=" in value and "HttpOnly" not in value and "Secure" in value
            for value in set_cookie_headers
        )
        assert all("SameSite=lax" in value for value in set_cookie_headers)
