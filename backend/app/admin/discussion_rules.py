from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/discussion-rules",
    tags=["admin-discussion-rules"],
    dependencies=[Depends(require_admin)],
)


class DiscussionRulesOut(BaseModel):
    silence_threshold_minutes: int
    speaking_ratio_min: float
    speaking_ratio_max: float
    cosine_similarity_threshold: float
    min_session_duration_minutes: int
    push_interval_minutes: int
    max_push_per_member: int
    analysis_enabled: bool
    updated_at: datetime


class DiscussionRulesUpdate(BaseModel):
    silence_threshold_minutes: int | None = Field(None, ge=1)
    speaking_ratio_min: float | None = Field(None, ge=0.0, le=1.0)
    speaking_ratio_max: float | None = Field(None, ge=0.0, le=1.0)
    cosine_similarity_threshold: float | None = Field(None, ge=0.0, le=1.0)
    min_session_duration_minutes: int | None = Field(None, ge=1)
    push_interval_minutes: int | None = Field(None, ge=1)
    max_push_per_member: int | None = Field(None, ge=1)
    analysis_enabled: bool | None = None


async def _get_rules(db: AsyncSession) -> DiscussionRulesOut:
    result = await db.execute(
        text(
            """
            SELECT silence_threshold_minutes, speaking_ratio_min, speaking_ratio_max,
                   cosine_similarity_threshold, min_session_duration_minutes,
                   push_interval_minutes, max_push_per_member,
                   analysis_enabled, updated_at
            FROM discussion_rules
            WHERE id = 'default'
            """
        )
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="规则配置缺失")
    return DiscussionRulesOut.model_validate(dict(row))


@router.get("/", response_model=DiscussionRulesOut)
async def get_discussion_rules(
    db: AsyncSession = Depends(get_db),
) -> DiscussionRulesOut:
    return await _get_rules(db)


@router.put("/", response_model=DiscussionRulesOut)
async def update_discussion_rules(
    payload: DiscussionRulesUpdate,
    db: AsyncSession = Depends(get_db),
) -> DiscussionRulesOut:
    sets: list[str] = []
    params: dict[str, Any] = {}

    if payload.silence_threshold_minutes is not None:
        sets.append("silence_threshold_minutes = :silence_threshold_minutes")
        params["silence_threshold_minutes"] = payload.silence_threshold_minutes
    if payload.speaking_ratio_min is not None:
        sets.append("speaking_ratio_min = :speaking_ratio_min")
        params["speaking_ratio_min"] = payload.speaking_ratio_min
    if payload.speaking_ratio_max is not None:
        sets.append("speaking_ratio_max = :speaking_ratio_max")
        params["speaking_ratio_max"] = payload.speaking_ratio_max
    if payload.cosine_similarity_threshold is not None:
        sets.append("cosine_similarity_threshold = :cosine_similarity_threshold")
        params["cosine_similarity_threshold"] = payload.cosine_similarity_threshold
    if payload.min_session_duration_minutes is not None:
        sets.append("min_session_duration_minutes = :min_session_duration_minutes")
        params["min_session_duration_minutes"] = payload.min_session_duration_minutes
    if payload.push_interval_minutes is not None:
        sets.append("push_interval_minutes = :push_interval_minutes")
        params["push_interval_minutes"] = payload.push_interval_minutes
    if payload.max_push_per_member is not None:
        sets.append("max_push_per_member = :max_push_per_member")
        params["max_push_per_member"] = payload.max_push_per_member
    if payload.analysis_enabled is not None:
        sets.append("analysis_enabled = :analysis_enabled")
        params["analysis_enabled"] = payload.analysis_enabled

    if not sets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个可更新字段",
        )

    sets.append("updated_at = NOW()")
    set_sql = ", ".join(sets)

    await db.execute(
        text(f"UPDATE discussion_rules SET {set_sql} WHERE id = 'default'"),
        params,
    )
    await db.commit()
    return await _get_rules(db)
