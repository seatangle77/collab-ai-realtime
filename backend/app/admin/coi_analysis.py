"""Admin API: CoI Cognitive Presence analysis."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.coi_analysis_service import (
    AnalysisMode,
    CoiAnalysisResult,
    build_coi_analysis,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin


router = APIRouter(
    prefix="/api/admin/coi-analysis",
    tags=["admin-coi-analysis"],
    dependencies=[Depends(require_admin)],
)


async def _load_rows(
    db: AsyncSession,
    group_ids: set[str],
) -> list[dict]:
    if not group_ids:
        return []
    result = await db.execute(
        text("""
            SELECT
                cu.session_id,
                cu.group_id,
                cu.coi_category,
                g.condition,
                g.name AS group_name
            FROM coi_utterances cu
            JOIN groups g ON g.id = cu.group_id
            WHERE cu.group_id = ANY(:group_ids)
            ORDER BY cu.session_id, cu.order_index
        """),
        {"group_ids": list(group_ids)},
    )
    return [dict(row) for row in result.mappings().all()]


class CreateCoiAnalysisPayload(ApiModel):
    mode: AnalysisMode = "two_conditions"
    group_ids_by_condition: dict[str, list[str]]


@router.post("/", response_model=CoiAnalysisResult)
async def create_coi_analysis(
    payload: CreateCoiAnalysisPayload,
    db: AsyncSession = Depends(get_db),
) -> CoiAnalysisResult:
    all_group_ids: set[str] = set()
    for group_ids in payload.group_ids_by_condition.values():
        all_group_ids.update(group_ids)

    rows = await _load_rows(db, all_group_ids)
    return build_coi_analysis(mode=payload.mode, rows=rows)
