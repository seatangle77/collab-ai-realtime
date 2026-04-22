"""
窗口指标接口（管理后台用）
- GET /api/sessions/{session_id}/window-metrics  获取最新窗口所有成员指标
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .admin.deps import require_admin
from .db import get_db

router = APIRouter(prefix="/api", tags=["window-metrics"])


class WindowMetricsOut(BaseModel):
    id: str
    session_id: str
    user_id: str
    window_start: Any
    window_end: Any
    speaking_ratio: float | None = None
    silence_s: int | None = None
    ttr: float | None = None
    arg_density: float | None = None
    srep: float | None = None
    info_gain: float | None = None
    has_reasoning: bool | None = None
    has_evidence: bool | None = None
    reasoning_source: str | None = None
    evidence_source: str | None = None
    created_at: Any


@router.get(
    "/sessions/{session_id}/window-metrics",
    response_model=list[WindowMetricsOut],
)
async def get_latest_window_metrics(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_admin),
) -> list[WindowMetricsOut]:
    """
    获取指定会话最新窗口（window_start 最大）的所有成员指标。
    仅管理员可访问。
    """
    # 1. 校验会话存在
    session_result = await db.execute(
        text("SELECT id FROM chat_sessions WHERE id = :session_id"),
        {"session_id": session_id},
    )
    if not session_result.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    # 2. 找最新 window_start
    latest_result = await db.execute(
        text(
            """
            SELECT MAX(window_start) AS latest_window
            FROM window_metrics
            WHERE session_id = :session_id
            """
        ),
        {"session_id": session_id},
    )
    latest_row = latest_result.mappings().first()
    latest_window = latest_row["latest_window"] if latest_row else None

    if not latest_window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该会话暂无窗口指标数据",
        )

    # 3. 返回该窗口所有成员的指标
    result = await db.execute(
        text(
            """
            SELECT id, session_id, user_id, window_start, window_end,
                   speaking_ratio, silence_s, ttr, arg_density,
                   srep, info_gain, has_reasoning, has_evidence,
                   reasoning_source, evidence_source, created_at
            FROM window_metrics
            WHERE session_id   = :session_id
              AND window_start = :window_start
            ORDER BY user_id
            """
        ),
        {"session_id": session_id, "window_start": latest_window},
    )
    rows = result.mappings().all()
    return [WindowMetricsOut.model_validate(dict(r)) for r in rows]
