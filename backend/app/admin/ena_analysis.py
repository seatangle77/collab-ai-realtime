"""Admin API: ENA (Epistemic Network Analysis) based on CoI coding results."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..analysis.ena_analysis_service import (
    AnalysisMode,
    EnaAnalysisResult,
    build_ena_analysis,
)
from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/ena-analysis",
    tags=["admin-ena-analysis"],
    dependencies=[Depends(require_admin)],
)


class CreateEnaAnalysisPayload(ApiModel):
    mode: AnalysisMode = "two_conditions"
    group_ids_by_condition: dict[str, list[str]]


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
                cu.order_index,
                cu.coi_category,
                cu.start_time,
                g.condition
            FROM coi_utterances cu
            JOIN groups g ON g.id = cu.group_id
            WHERE cu.group_id = ANY(:group_ids)
              AND cu.coi_category IS NOT NULL
            ORDER BY cu.session_id, cu.order_index
        """),
        {"group_ids": list(group_ids)},
    )
    return [dict(row) for row in result.mappings().all()]


@router.post("/", response_model=EnaAnalysisResult)
async def create_ena_analysis(
    payload: CreateEnaAnalysisPayload,
    db: AsyncSession = Depends(get_db),
) -> EnaAnalysisResult:
    all_group_ids: set[str] = set()
    for group_ids in payload.group_ids_by_condition.values():
        all_group_ids.update(group_ids)

    rows = await _load_rows(db, all_group_ids)
    return build_ena_analysis(mode=payload.mode, rows=rows)
