from __future__ import annotations

from datetime import datetime
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.task_score_config import TASK_SCORE_CONFIG
from ..analysis.task_score_service import (
    TaskScoreAnswers,
    TaskScoreEntryPayload,
    TaskScoreResult,
    calculate_task_score_result,
    model_to_jsonable,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin


router = APIRouter(
    prefix="/api/admin/task-score-entries",
    tags=["admin-task-score-entries"],
    dependencies=[Depends(require_admin)],
)


class TaskScoreEntryOut(ApiModel):
    id: str
    group_id: str
    task_id: str
    condition: str
    answers_json: dict[str, Any]
    result_json: dict[str, Any] | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


async def _get_group_condition_or_404(group_id: str, db: AsyncSession) -> str:
    result = await db.execute(
        text("SELECT condition FROM groups WHERE id = :group_id"),
        {"group_id": group_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群组不存在")
    return row["condition"]


def _normalize_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


@router.get("/", response_model=TaskScoreEntryOut | None)
async def get_task_score_entry(
    group_id: str = Query(...),
    task_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> TaskScoreEntryOut | None:
    if task_id not in TASK_SCORE_CONFIG:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="task_id 无效")

    result = await db.execute(
        text(
            """
            SELECT id, group_id, task_id, condition, answers_json, result_json,
                   created_by, created_at, updated_at
            FROM task_score_entries
            WHERE group_id = :group_id AND task_id = :task_id
            """
        ),
        {"group_id": group_id, "task_id": task_id},
    )
    row = result.mappings().first()
    if not row:
        return None

    data = dict(row)
    data["answers_json"] = _normalize_jsonb(data["answers_json"])
    data["result_json"] = _normalize_jsonb(data["result_json"])
    return TaskScoreEntryOut.model_validate(data)


@router.post("/", response_model=TaskScoreEntryOut)
async def save_task_score_entry(
    payload: TaskScoreEntryPayload,
    db: AsyncSession = Depends(get_db),
) -> TaskScoreEntryOut:
    if payload.task_id not in TASK_SCORE_CONFIG:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="task_id 无效")

    condition = await _get_group_condition_or_404(payload.group_id, db)
    result_json = calculate_task_score_result(payload.task_id, payload.answers)
    entry_id = f"tse{uuid.uuid4().hex[:10]}"

    result = await db.execute(
        text(
            """
            INSERT INTO task_score_entries (
                id, group_id, task_id, condition,
                answers_json, result_json, created_by, created_at, updated_at
            )
            VALUES (
                :id, :group_id, :task_id, :condition,
                CAST(:answers_json AS jsonb), CAST(:result_json AS jsonb),
                NULL, NOW(), NOW()
            )
            ON CONFLICT (group_id, task_id)
            DO UPDATE SET
                condition = EXCLUDED.condition,
                answers_json = EXCLUDED.answers_json,
                result_json = EXCLUDED.result_json,
                updated_at = NOW()
            RETURNING id, group_id, task_id, condition, answers_json, result_json,
                      created_by, created_at, updated_at
            """
        ),
        {
            "id": entry_id,
            "group_id": payload.group_id,
            "task_id": payload.task_id,
            "condition": condition,
            "answers_json": json.dumps(model_to_jsonable(payload.answers), ensure_ascii=False),
            "result_json": json.dumps(model_to_jsonable(result_json), ensure_ascii=False),
        },
    )
    row = result.mappings().first()
    await db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="保存任务分数失败")

    data = dict(row)
    data["answers_json"] = _normalize_jsonb(data["answers_json"])
    data["result_json"] = _normalize_jsonb(data["result_json"])
    return TaskScoreEntryOut.model_validate(data)


@router.post("/preview", response_model=TaskScoreResult)
async def preview_task_score_entry(payload: TaskScoreEntryPayload) -> TaskScoreResult:
    return calculate_task_score_result(payload.task_id, payload.answers)

