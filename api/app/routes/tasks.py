import uuid

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_task
from ..deps import (
    _now_iso,
    _register_task,
    _set_task_status,
    require_admin,
)
from ..schemas import (
    BackgroundClassifyRequest,
    TaskQueuedResponse,
    TaskStatusResponse,
)

router = APIRouter()


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def task_status(task_id: str) -> TaskStatusResponse:
    task = await get_task(task_id)
    if not task:
        inferred_type = "missing"
        try:
            uuid.UUID(task_id)
            inferred_type = "expired"
        except (ValueError, TypeError, AttributeError):
            inferred_type = "missing"
        now = _now_iso()
        return TaskStatusResponse(
            task_id=task_id,
            status="failed",
            task_type=inferred_type,
            created_at=now,
            started_at=None,
            finished_at=now,
            message="Task record unavailable (expired or cleaned)",
            result=None,
            cursor_full_name=None,
            retry_from_task_id=None,
        )
    response_data = {key: task.get(key) for key in TaskStatusResponse.model_fields}
    return TaskStatusResponse(**response_data)


@router.post(
    "/tasks/{task_id}/retry",
    response_model=TaskQueuedResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def retry_task(task_id: str) -> TaskQueuedResponse:
    from .classify import _start_background_classify

    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("task_type") != "classify":
        raise HTTPException(status_code=400, detail="Retry is only supported for classify tasks")
    if task.get("status") in ("running", "processing", "queued"):
        raise HTTPException(status_code=409, detail="Task is still running or queued")
    payload = task.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Task payload not found")

    cursor_full_name = task.get("cursor_full_name")
    try:
        request_payload = BackgroundClassifyRequest(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid task payload: {exc}") from exc
    if request_payload.force and cursor_full_name:
        request_payload = BackgroundClassifyRequest(
            **{**request_payload.model_dump(), "cursor_full_name": cursor_full_name}
        )

    new_task_id = str(uuid.uuid4())
    await _register_task(
        new_task_id,
        "classify",
        f"Retry of {task_id}",
        payload=request_payload.model_dump(),
        retry_from_task_id=task_id,
    )
    started = await _start_background_classify(request_payload, new_task_id, allow_fallback=False)
    if not started:
        await _set_task_status(
            new_task_id,
            "failed",
            finished_at=_now_iso(),
            message="Classification already running",
        )
        raise HTTPException(status_code=409, detail="Classification already running")
    return TaskQueuedResponse(task_id=new_task_id, status="queued", message="Retry queued")
