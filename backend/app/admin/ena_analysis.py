"""Admin API: ENA (Epistemic Network Analysis) based on final CoI codes."""
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
    """Load finalized CoI unit codes for ENA window co-occurrence analysis."""
    if not group_ids:
        return []
    result = await db.execute(
        text("""
            SELECT
                u.session_id,
                u.group_id,
                u.order_index,
                final_code.coi_category,
                u.start_time,
                g.condition
            FROM coi_units u
            JOIN groups g ON g.id = u.group_id
            JOIN coi_unit_codes final_code
              ON final_code.unit_id = u.id
             AND final_code.coder_role = 'final'
            WHERE u.group_id = ANY(:group_ids)
              AND final_code.coi_category IS NOT NULL
            ORDER BY u.session_id, u.order_index
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
