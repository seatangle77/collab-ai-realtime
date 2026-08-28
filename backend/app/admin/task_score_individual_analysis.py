"""Admin API for read-only individual-to-group task-score change analysis."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.task_score_analysis_service import AnalysisMode, TaskFilter
from ..analysis.task_score_individual_analysis_service import (
    TaskScoreIndividualAnalysisResult,
    build_task_score_individual_analysis,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin


router = APIRouter(
    prefix="/api/admin/task-score-individual-analysis",
    tags=["admin-task-score-individual-analysis"],
    dependencies=[Depends(require_admin)],
)


def _normalize_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class TaskScoreIndividualAnalysisRequest(ApiModel):
    mode: AnalysisMode = "two_conditions"
    task_id: TaskFilter = "all"
    group_ids_by_condition: dict[str, list[str]]


async def _load_rows(db: AsyncSession, group_ids: set[str]) -> list[dict[str, Any]]:
    if not group_ids:
        return []
    result = await db.execute(
        text(
            """
            SELECT id, group_id, task_id, condition, result_json
            FROM task_score_entries
            WHERE result_json IS NOT NULL
              AND group_id = ANY(:group_ids)
            ORDER BY updated_at DESC
            """
        ),
        {"group_ids": list(group_ids)},
    )
    rows: list[dict[str, Any]] = []
    for row in result.mappings().all():
        data = dict(row)
        data["result_json"] = _normalize_jsonb(data["result_json"])
        rows.append(data)
    return rows


@router.post("/", response_model=TaskScoreIndividualAnalysisResult)
async def create_task_score_individual_analysis(
    payload: TaskScoreIndividualAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> TaskScoreIndividualAnalysisResult:
    selected_by_condition = {
        condition: set(group_ids)
        for condition, group_ids in payload.group_ids_by_condition.items()
    }
    all_group_ids = set().union(*selected_by_condition.values()) if selected_by_condition else set()
    rows = [
        row
        for row in await _load_rows(db, all_group_ids)
        if row.get("group_id") in selected_by_condition.get(str(row.get("condition")), set())
    ]
    return build_task_score_individual_analysis(mode=payload.mode, task_id=payload.task_id, rows=rows)
