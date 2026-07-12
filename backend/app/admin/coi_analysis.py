"""Admin API: CoI Cognitive Presence analysis."""
from __future__ import annotations

from typing import Literal

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

CoderRole = Literal["final", "coder_a", "coder_b"]

router = APIRouter(
    prefix="/api/admin/coi-analysis",
    tags=["admin-coi-analysis"],
    dependencies=[Depends(require_admin)],
)


async def _load_rows(
    db: AsyncSession,
    group_ids: set[str],
    coder_role: CoderRole,
) -> list[dict]:
    """Load CoI unit rows with the selected coding role.

    The analysis now uses the new workflow tables:
    - coi_units provides the finalized analysis units.
    - coi_unit_codes provides codes for final/coder_a/coder_b.

    Units without a selected-role code are included with coi_categories=NULL so the
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
                selected_code.coi_categories,
                g.condition,
                g.name AS group_name
            FROM coi_units u
            JOIN groups g ON g.id = u.group_id
            LEFT JOIN coi_unit_codes selected_code
              ON selected_code.unit_id = u.id
             AND selected_code.coder_role = :coder_role
            WHERE u.group_id = ANY(:group_ids)
            ORDER BY u.session_id, u.order_index
        """),
        {"group_ids": list(group_ids), "coder_role": coder_role},
    )
    return [dict(row) for row in result.mappings().all()]


class CreateCoiAnalysisPayload(ApiModel):
    mode: AnalysisMode = "two_conditions"
    group_ids_by_condition: dict[str, list[str]]
    coder_role: CoderRole = "final"


@router.post("/", response_model=CoiAnalysisResult)
async def create_coi_analysis(
    payload: CreateCoiAnalysisPayload,
    db: AsyncSession = Depends(get_db),
) -> CoiAnalysisResult:
    all_group_ids: set[str] = set()
    for group_ids in payload.group_ids_by_condition.values():
        all_group_ids.update(group_ids)

    rows = await _load_rows(db, all_group_ids, payload.coder_role)
    return build_coi_analysis(mode=payload.mode, rows=rows)
