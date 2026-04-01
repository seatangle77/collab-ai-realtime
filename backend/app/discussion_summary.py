"""
讨论摘要接口
- GET /api/sessions/{session_id}/summary  获取最新一条讨论摘要
"""
from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db

router = APIRouter(prefix="/api", tags=["discussion-summary"])


class DiscussionSummaryOut(BaseModel):
    id: str
    session_id: str
    version: int
    content: str
    window_start: Any
    window_end: Any
    created_at: Any


@router.get(
    "/sessions/{session_id}/summary",
    response_model=DiscussionSummaryOut,
)
async def get_latest_summary(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> DiscussionSummaryOut:
    """
    获取指定会话的最新讨论摘要（version 最大的一条）。
    仅会话活跃成员可访问。
    """
    # 1. 校验会话存在且当前用户是活跃成员
    member_result = await db.execute(
        text(
            """
            SELECT 1 FROM chat_sessions cs
            JOIN group_memberships gm ON gm.group_id = cs.group_id
            WHERE cs.id    = :session_id
              AND gm.user_id = :user_id
              AND gm.status  = 'active'
            """
        ),
        {"session_id": session_id, "user_id": current_user["id"]},
    )
    if not member_result.first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅会话活跃成员可访问",
        )

    # 2. 取 version 最大的摘要
    result = await db.execute(
        text(
            """
            SELECT id, session_id, version, content, window_start, window_end, created_at
            FROM discussion_summaries
            WHERE session_id = :session_id
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {"session_id": session_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该会话暂无讨论摘要",
        )

    return DiscussionSummaryOut.model_validate(dict(row))
