from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.task_score_analysis_service import (
    AnalysisMode,
    TaskFilter,
    TaskScoreAnalysisResult,
    build_task_score_analysis,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin


router = APIRouter(
    prefix="/api/admin/task-score-analysis",
    tags=["admin-task-score-analysis"],
    dependencies=[Depends(require_admin)],
)


def _normalize_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class TaskScoreAnalysisRequest(ApiModel):
    mode: AnalysisMode = "two_conditions"
    task_id: TaskFilter = "all"
    group_ids_by_condition: dict[str, list[str]]


async def _load_task_score_rows(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT id, group_id, task_id, condition, result_json
            FROM task_score_entries
            WHERE result_json IS NOT NULL
            ORDER BY updated_at DESC
            """
        )
    )
    rows = []
    for row in result.mappings().all():
        data = dict(row)
        data["result_json"] = _normalize_jsonb(data["result_json"])
        rows.append(data)
    return rows


@router.get("/", response_model=TaskScoreAnalysisResult)
async def get_task_score_analysis(
    mode: AnalysisMode = Query("two_conditions"),
    task_id: TaskFilter = Query("all"),
    db: AsyncSession = Depends(get_db),
) -> TaskScoreAnalysisResult:
    rows = await _load_task_score_rows(db)
    return build_task_score_analysis(mode=mode, task_id=task_id, rows=rows)


@router.post("/", response_model=TaskScoreAnalysisResult)
async def create_task_score_analysis(
    payload: TaskScoreAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> TaskScoreAnalysisResult:
    selected_group_ids = {
        condition: set(group_ids)
        for condition, group_ids in payload.group_ids_by_condition.items()
    }
    rows = [
        row
        for row in await _load_task_score_rows(db)
        if row.get("group_id") in selected_group_ids.get(str(row.get("condition")), set())
    ]
    return build_task_score_analysis(mode=payload.mode, task_id=payload.task_id, rows=rows)
