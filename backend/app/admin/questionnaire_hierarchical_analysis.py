"""Read-only admin API for cluster-aware questionnaire analysis."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.questionnaire_analysis_service import AnalysisMode, ScaleKind
from ..analysis.questionnaire_hierarchical_analysis_service import (
    QuestionnaireHierarchicalAnalysisResult,
    build_questionnaire_hierarchical_analysis,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin
from .questionnaire_analysis import _load_rows


router = APIRouter(
    prefix="/api/admin/questionnaire-hierarchical-analysis",
    tags=["admin-questionnaire-hierarchical-analysis"],
    dependencies=[Depends(require_admin)],
)


class CreateQuestionnaireHierarchicalAnalysisPayload(ApiModel):
    scale: ScaleKind = "srcc"
    mode: AnalysisMode = "two_conditions"
    group_ids_by_condition: dict[str, list[str]]


@router.post("/", response_model=QuestionnaireHierarchicalAnalysisResult)
async def create_questionnaire_hierarchical_analysis(
    payload: CreateQuestionnaireHierarchicalAnalysisPayload,
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireHierarchicalAnalysisResult:
    selected = {condition: set(group_ids) for condition, group_ids in payload.group_ids_by_condition.items()}
    rows = [
        row for row in await _load_rows(db)
        if row.get("group_id") in selected.get(str(row.get("condition")), set())
    ]
    return build_questionnaire_hierarchical_analysis(scale=payload.scale, mode=payload.mode, rows=rows)
