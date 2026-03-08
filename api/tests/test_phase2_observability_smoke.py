import asyncio
import uuid

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from api.app import deps as deps_mod
from api.app import main as main_mod
from api.app import state as state_mod
from api.app.observability import REQUEST_ID_HEADER, get_request_id


def _run(coro):
    return asyncio.run(coro)


def _build_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "state": {},
    }
    return Request(scope, _receive)


def test_request_context_middleware_reuses_request_id_and_records_success_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_metrics: list[dict[str, int]] = []

    async def _fake_add_quality_metrics(**delta: int) -> None:
        recorded_metrics.append(delta)

    async def _call_next(request: Request) -> JSONResponse:
        assert request.state.request_id == "request-123"
        assert get_request_id() == "request-123"
        return JSONResponse({"ok": True})

    monkeypatch.setattr(main_mod, "_add_quality_metrics", _fake_add_quality_metrics)

    response = _run(
        main_mod.request_context_middleware(
            _build_request(headers=[(b"x-request-id", b"request-123")]),
            _call_next,
        )
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "request-123"
    assert len(recorded_metrics) == 1
    metrics = recorded_metrics[0]
    assert metrics["api_request_total"] == 1
    assert metrics["api_error_total"] == 0
    assert metrics["api_request_latency_ms_total"] >= 0


def test_request_context_middleware_generates_request_id_and_counts_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_metrics: list[dict[str, int]] = []
    seen_request_id: dict[str, str] = {}

    async def _fake_add_quality_metrics(**delta: int) -> None:
        recorded_metrics.append(delta)

    async def _call_next(request: Request) -> JSONResponse:
        request_id = get_request_id()
        assert request_id is not None
        assert request.state.request_id == request_id
        seen_request_id["value"] = request_id
        return JSONResponse({"detail": "boom"}, status_code=500)

    monkeypatch.setattr(main_mod, "_add_quality_metrics", _fake_add_quality_metrics)

    response = _run(
        main_mod.request_context_middleware(
            _build_request(),
            _call_next,
        )
    )

    generated_request_id = seen_request_id["value"]
    assert str(uuid.UUID(generated_request_id)) == generated_request_id
    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == generated_request_id
    assert len(recorded_metrics) == 1
    metrics = recorded_metrics[0]
    assert metrics["api_request_total"] == 1
    assert metrics["api_error_total"] == 1
    assert metrics["api_request_latency_ms_total"] >= 0


def test_request_context_middleware_records_metrics_for_raised_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_metrics: list[dict[str, int]] = []

    async def _fake_add_quality_metrics(**delta: int) -> None:
        recorded_metrics.append(delta)

    async def _call_next(_request: Request) -> JSONResponse:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod, "_add_quality_metrics", _fake_add_quality_metrics)

    with pytest.raises(RuntimeError, match="boom"):
        _run(
            main_mod.request_context_middleware(
                _build_request(headers=[(b"x-request-id", b"request-raise")]),
                _call_next,
            )
        )

    assert len(recorded_metrics) == 1
    metrics = recorded_metrics[0]
    assert metrics["api_request_total"] == 1
    assert metrics["api_error_total"] == 1
    assert metrics["api_request_latency_ms_total"] >= 0


def test_unhandled_exception_handler_attaches_request_id_header() -> None:
    request = _build_request(headers=[(b"x-request-id", b"request-handler")])
    request.state.request_id = "request-handler"

    response = _run(
        main_mod.unhandled_exception_handler(
            request,
            RuntimeError("boom"),
        )
    )

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == "request-handler"
    assert response.body == b'{"detail":"Internal Server Error"}'


def test_quality_metrics_derive_observability_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        state_mod,
        "quality_metrics",
        {
            "classification_total": 8,
            "rule_hit_total": 6,
            "ai_fallback_total": 2,
            "empty_tag_total": 1,
            "uncategorized_total": 1,
            "search_total": 4,
            "search_zero_result_total": 1,
            "api_request_total": 4,
            "api_error_total": 1,
            "api_request_latency_ms_total": 120,
            "task_queued_total": 5,
            "task_finished_total": 3,
            "task_failed_total": 2,
            "cache_hit_total": 6,
            "cache_miss_total": 2,
            "db_lock_conflict_total": 0,
            "db_lock_retry_total": 0,
            "db_lock_retry_exhausted_total": 0,
        },
    )

    metrics = _run(state_mod._get_quality_metrics())

    assert metrics["rule_hit_rate"] == 0.75
    assert metrics["search_zero_result_rate"] == 0.25
    assert metrics["api_error_rate"] == 0.25
    assert metrics["api_request_latency_ms_avg"] == 30
    assert metrics["task_failure_rate"] == 0.4
    assert metrics["cache_hit_rate"] == 0.75


def test_task_registration_and_status_updates_emit_observability_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_tasks: list[dict[str, object]] = []
    updated_tasks: list[dict[str, object]] = []
    metric_calls: list[dict[str, int]] = []

    async def _fake_create_task(
        task_id: str,
        task_type: str,
        status: str,
        message: str | None = None,
        payload: dict | None = None,
        retry_from_task_id: str | None = None,
    ) -> None:
        created_tasks.append(
            {
                "task_id": task_id,
                "task_type": task_type,
                "status": status,
                "message": message,
                "payload": payload,
                "retry_from_task_id": retry_from_task_id,
            }
        )

    async def _fake_update_task(task_id: str, status: str, **updates: object) -> None:
        updated_tasks.append(
            {
                "task_id": task_id,
                "status": status,
                **updates,
            }
        )

    async def _fake_add_quality_metrics(**delta: int) -> None:
        metric_calls.append(delta)

    monkeypatch.setattr(deps_mod, "create_task", _fake_create_task)
    monkeypatch.setattr(deps_mod, "update_task", _fake_update_task)
    monkeypatch.setattr(deps_mod, "_add_quality_metrics", _fake_add_quality_metrics)

    _run(
        deps_mod._register_task(
            "task-sync-1",
            "sync",
            message="queued",
            payload={"full": True},
        )
    )
    _run(
        deps_mod._set_task_status(
            "task-sync-1",
            "finished",
            finished_at="2026-03-08T00:00:00+00:00",
        )
    )
    _run(
        deps_mod._set_task_status(
            "task-sync-2",
            "failed",
            finished_at="2026-03-08T00:01:00+00:00",
            message="boom",
        )
    )

    assert created_tasks == [
        {
            "task_id": "task-sync-1",
            "task_type": "sync",
            "status": "queued",
            "message": "queued",
            "payload": {"full": True},
            "retry_from_task_id": None,
        }
    ]
    assert updated_tasks[0]["status"] == "finished"
    assert updated_tasks[1]["status"] == "failed"
    assert metric_calls == [
        {"task_queued_total": 1},
        {"task_finished_total": 1},
        {"task_failed_total": 1},
    ]
