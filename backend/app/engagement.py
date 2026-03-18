from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db

router = APIRouter(prefix="/api", tags=["engagement"])


class MemberMetricsItem(BaseModel):
    user_id: str
    user_name: str | None = None
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


class EngagementSnapshotOut(BaseModel):
    calculated_at: datetime | None = None
    members: list[MemberMetricsItem] = []


@router.get(
    "/sessions/{session_id}/engagement",
    response_model=EngagementSnapshotOut,
)
async def get_session_engagement(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> EngagementSnapshotOut:
    """
    获取该会话最近一次计算的全组参与度指标快照。
    每位成员只返回 calculated_at 最新的一条记录。
    """
    # 1. 校验会话存在
    session_result = await db.execute(
        text("SELECT group_id FROM chat_sessions WHERE id = :id"),
        {"id": session_id},
    )
    session_row = session_result.mappings().first()
    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    group_id = session_row["group_id"]

    # 2. 校验当前用户是该群组 active 成员
    membership_result = await db.execute(
        text(
            """
            SELECT 1 FROM group_memberships
            WHERE group_id = :group_id AND user_id = :user_id AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    if not membership_result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅群组成员可以查看参与度数据")

    # 3. 每位成员取最新一条（DISTINCT ON user_id ORDER BY calculated_at DESC）
    result = await db.execute(
        text(
            """
            SELECT DISTINCT ON (em.user_id)
                em.user_id,
                em.calculated_at,
                em.speaking_ratio,
                em.speaking_frequency,
                em.silence_duration_s,
                em.mattr_score,
                em.avg_sentence_length,
                em.response_rate,
                em.new_idea_rate,
                em.topic_cosine_similarity,
                em.semantic_cohesion,
                em.semantic_uniqueness,
                u.name AS user_name
            FROM engagement_metrics em
            LEFT JOIN users_info u ON u.id = em.user_id
            WHERE em.session_id = :session_id
            ORDER BY em.user_id, em.calculated_at DESC
            """
        ),
        {"session_id": session_id},
    )
    rows = result.mappings().all()

    if not rows:
        return EngagementSnapshotOut(calculated_at=None, members=[])

    # calculated_at 取所有记录中最大值
    calculated_at = max(row["calculated_at"] for row in rows)

    members = [
        MemberMetricsItem(
            user_id=row["user_id"],
            user_name=row.get("user_name"),
            speaking_ratio=row.get("speaking_ratio"),
            speaking_frequency=row.get("speaking_frequency"),
            silence_duration_s=row.get("silence_duration_s"),
            mattr_score=row.get("mattr_score"),
            avg_sentence_length=row.get("avg_sentence_length"),
            response_rate=row.get("response_rate"),
            new_idea_rate=row.get("new_idea_rate"),
            topic_cosine_similarity=row.get("topic_cosine_similarity"),
            semantic_cohesion=row.get("semantic_cohesion"),
            semantic_uniqueness=row.get("semantic_uniqueness"),
        )
        for row in rows
    ]

    return EngagementSnapshotOut(calculated_at=calculated_at, members=members)
