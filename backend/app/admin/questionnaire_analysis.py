"""Admin API: questionnaire analysis (SRCC & PCS)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.questionnaire_analysis_service import (
    AnalysisMode,
    QuestionnaireAnalysisResult,
    ScaleKind,
    build_questionnaire_analysis,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin


router = APIRouter(
    prefix="/api/admin/questionnaire-analysis",
    tags=["admin-questionnaire-analysis"],
    dependencies=[Depends(require_admin)],
)


def _normalize_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


async def _load_rows(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT user_id, group_id, condition,
                   srcc_responses, srcc_result,
                   pcs_responses, pcs_result
            FROM questionnaire_entries
            ORDER BY created_at DESC
        """)
    )
    rows = []
    for row in result.mappings().all():
        data = dict(row)
        for key in ("srcc_responses", "srcc_result", "pcs_responses", "pcs_result"):
            data[key] = _normalize_jsonb(data[key])
        rows.append(data)
    return rows


class CreateQuestionnaireAnalysisPayload(ApiModel):
    scale: ScaleKind = "srcc"
    mode: AnalysisMode = "two_conditions"
    group_ids_by_condition: dict[str, list[str]]


@router.get("/", response_model=QuestionnaireAnalysisResult)
async def get_questionnaire_analysis(
    scale: ScaleKind = Query("srcc"),
    mode: AnalysisMode = Query("two_conditions"),
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireAnalysisResult:
    rows = await _load_rows(db)
    return build_questionnaire_analysis(scale=scale, mode=mode, rows=rows)


@router.post("/", response_model=QuestionnaireAnalysisResult)
async def create_questionnaire_analysis(
    payload: CreateQuestionnaireAnalysisPayload,
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireAnalysisResult:
    selected_group_ids = {
        condition: set(group_ids)
        for condition, group_ids in payload.group_ids_by_condition.items()
    }
    all_rows = await _load_rows(db)
    rows = [
        row for row in all_rows
        if row.get("group_id") in selected_group_ids.get(str(row.get("condition")), set())
    ]
    return build_questionnaire_analysis(scale=payload.scale, mode=payload.mode, rows=rows)
