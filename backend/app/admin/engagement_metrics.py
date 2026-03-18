from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(
    prefix="/api/admin/engagement-metrics",
    tags=["admin-engagement-metrics"],
    dependencies=[Depends(require_admin)],
)

VALID_STATE_TYPES = {
    "low_participation", "over_dominance", "disengaged",
    "deadlock", "topic_drift", "low_depth", "homogeneous",
}


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminEngagementMetricOut(BaseModel):
    id: str
    session_id: str
    user_id: str
    user_name: str | None = None
    calculated_at: Any
    speaking_ratio: float | None = None
    speaking_frequency: float | None = None
    silence_duration_s: int | None = None
    mattr_score: float | None = None
    avg_sentence_length: float | None = None
    response_rate: float | None = None
    new_idea_rate: float | None = None
    topic_cosine_similarity: float | None = None
    semantic_cohesion: float | None = None
    semantic_uniqueness: float | None = None


class AdminEngagementMetricCreate(BaseModel):
    session_id: str
    user_id: str
    calculated_at: datetime | None = None
    speaking_ratio: float | None = None
    speaking_frequency: float | None = None
    silence_duration_s: int | None = None
    mattr_score: float | None = None
    avg_sentence_length: float | None = None
    response_rate: float | None = None
    new_idea_rate: float | None = None
    topic_cosine_similarity: float | None = None
    semantic_cohesion: float | None = None
    semantic_uniqueness: float | None = None


@router.post(
    "/",
    response_model=AdminEngagementMetricOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_engagement_metric(
    payload: AdminEngagementMetricCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminEngagementMetricOut:
    # 校验 session 存在
    r = await db.execute(
        text("SELECT id FROM chat_sessions WHERE id = :id"),
        {"id": payload.session_id},
    )
    if not r.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 校验 user 存在
    r2 = await db.execute(
        text("SELECT id, name FROM users_info WHERE id = :id"),
        {"id": payload.user_id},
    )
    user_row = r2.mappings().first()
    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    metric_id = f"em{uuid.uuid4().hex[:8]}"
    calculated_at = _to_utc_naive(payload.calculated_at) if payload.calculated_at else None

    result = await db.execute(
        text(
            """
            INSERT INTO engagement_metrics (
                id, session_id, user_id, calculated_at,
                speaking_ratio, speaking_frequency, silence_duration_s,
                mattr_score, avg_sentence_length, response_rate, new_idea_rate,
                topic_cosine_similarity, semantic_cohesion, semantic_uniqueness
            ) VALUES (
                :id, :session_id, :user_id,
                COALESCE(:calculated_at, NOW()),
                :speaking_ratio, :speaking_frequency, :silence_duration_s,
                :mattr_score, :avg_sentence_length, :response_rate, :new_idea_rate,
                :topic_cosine_similarity, :semantic_cohesion, :semantic_uniqueness
            )
            RETURNING id, session_id, user_id, calculated_at,
                      speaking_ratio, speaking_frequency, silence_duration_s,
                      mattr_score, avg_sentence_length, response_rate, new_idea_rate,
                      topic_cosine_similarity, semantic_cohesion, semantic_uniqueness
            """
        ),
        {
            "id": metric_id,
            "session_id": payload.session_id,
            "user_id": payload.user_id,
            "calculated_at": calculated_at,
            "speaking_ratio": payload.speaking_ratio,
            "speaking_frequency": payload.speaking_frequency,
            "silence_duration_s": payload.silence_duration_s,
            "mattr_score": payload.mattr_score,
            "avg_sentence_length": payload.avg_sentence_length,
            "response_rate": payload.response_rate,
            "new_idea_rate": payload.new_idea_rate,
            "topic_cosine_similarity": payload.topic_cosine_similarity,
            "semantic_cohesion": payload.semantic_cohesion,
            "semantic_uniqueness": payload.semantic_uniqueness,
        },
    )
    await db.commit()
    row = result.mappings().one()
    return AdminEngagementMetricOut(
        **dict(row),
        user_name=user_row.get("name"),
    )


@router.get("/", response_model=Page[AdminEngagementMetricOut])
async def list_engagement_metrics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    user_id: str | None = None,
    calculated_from: datetime | None = None,
    calculated_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminEngagementMetricOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("em.session_id = :session_id")
        params["session_id"] = session_id
    if user_id:
        where.append("em.user_id = :user_id")
        params["user_id"] = user_id
    if calculated_from:
        where.append("em.calculated_at >= :calculated_from")
        params["calculated_from"] = _to_utc_naive(calculated_from)
    if calculated_to:
        where.append("em.calculated_at <= :calculated_to")
        params["calculated_to"] = _to_utc_naive(calculated_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM engagement_metrics em WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                em.id, em.session_id, em.user_id, em.calculated_at,
                em.speaking_ratio, em.speaking_frequency, em.silence_duration_s,
                em.mattr_score, em.avg_sentence_length, em.response_rate,
                em.new_idea_rate, em.topic_cosine_similarity,
                em.semantic_cohesion, em.semantic_uniqueness,
                u.name AS user_name
            FROM engagement_metrics em
            LEFT JOIN users_info u ON u.id = em.user_id
            WHERE {where_sql}
            ORDER BY em.calculated_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminEngagementMetricOut.model_validate(dict(row)) for row in rows]

    return Page[AdminEngagementMetricOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )
