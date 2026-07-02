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
    """Load CoI unit rows with final agreed codes.

    The analysis now uses the new workflow tables:
    - coi_units provides the finalized analysis units.
    - coi_unit_codes with coder_role='final' provides agreed codes.

    Units without a final code are included with coi_category=NULL so the
    analysis service can report them as uncoded/excluded instead of silently
    hiding incomplete sessions.
    """
    if not group_ids:
        return []
    result = await db.execute(
        text("""
            SELECT
                u.session_id,
                u.group_id,
                final_code.coi_category,
                g.condition,
                g.name AS group_name
            FROM coi_units u
            JOIN groups g ON g.id = u.group_id
            LEFT JOIN coi_unit_codes final_code
              ON final_code.unit_id = u.id
             AND final_code.coder_role = 'final'
            WHERE u.group_id = ANY(:group_ids)
            ORDER BY u.session_id, u.order_index
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
