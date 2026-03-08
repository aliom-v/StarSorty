from fastapi import APIRouter, Depends, HTTPException

from ..db import get_task
from ..deps import (
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
        raise HTTPException(status_code=404, detail="Task not found")
    response_data = {key: task.get(key) for key in TaskStatusResponse.model_fields}
    return TaskStatusResponse(**response_data)


@router.post(
    "/tasks/{task_id}/retry",
    response_model=TaskQueuedResponse,
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def retry_task(task_id: str) -> TaskQueuedResponse:
    from .classify import _queue_background_classify_task

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

    new_task_id = await _queue_background_classify_task(
        request_payload,
        message=f"Retry of {task_id}",
        retry_from_task_id=task_id,
        allow_fallback=False,
    )
    if new_task_id is None:
        raise HTTPException(status_code=409, detail="Classification already running")
    return TaskQueuedResponse(task_id=new_task_id, status="queued", message="Retry queued")
