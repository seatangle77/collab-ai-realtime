"""
讨论摘要接口
- GET  /api/sessions/{session_id}/summary          获取最新一条讨论摘要
- POST /api/internal/sessions/{session_id}/summary Agent 写库并广播（需 X-Admin-Token）
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .admin.deps import require_admin
from .auth import get_current_user
from .db import get_db
from .ws_manager import ws_manager
from .ws_protocol import build_summary_update

router = APIRouter(prefix="/api", tags=["discussion-summary"])


class DiscussionSummaryOut(BaseModel):
    id: str
    session_id: str
    version: int
    content: str
    analysis_run_id: str
    window_start: Any
    window_end: Any
    created_at: Any


class SummaryNotifyIn(BaseModel):
    content: str
    window_start: datetime
    window_end: datetime


def _to_utc_naive(dt: datetime) -> datetime:
    """
    Normalize datetimes for DB writes.
    The table currently stores naive timestamps, while API input may be timezone-aware.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def _build_summary_run_id(session_id: str, window_start: Any) -> str:
    value = window_start.isoformat() if hasattr(window_start, "isoformat") else str(window_start)
    return f"summary:{session_id}:{value}"


@router.post(
    "/internal/sessions/{session_id}/summary",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def notify_summary(
    session_id: str,
    body: SummaryNotifyIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Agent 写摘要并广播。
    1. 取当前最大 version + 1
    2. 写入 discussion_summaries
    3. WebSocket 广播 summary_update 给会话所有人
    """
    # 1. 原子写库：version = MAX(version)+1，避免并发竞争
    summary_id = "ds" + uuid.uuid4().hex[:8]
    insert_result = await db.execute(
        text(
            """
            INSERT INTO discussion_summaries (id, session_id, version, content, window_start, window_end, created_at)
            SELECT :id, :session_id, COALESCE(MAX(version), 0) + 1, :content, :window_start, :window_end, NOW()
            FROM discussion_summaries
            WHERE session_id = :session_id
            RETURNING id, version, window_start, window_end, created_at
            """
        ),
        {
            "id": summary_id,
            "session_id": session_id,
            "content": body.content,
            "window_start": _to_utc_naive(body.window_start),
            "window_end": _to_utc_naive(body.window_end),
        },
    )
    inserted_row = insert_result.mappings().first()
    new_version = inserted_row["version"]
    await db.commit()

    # 3. WebSocket 广播
    await ws_manager.broadcast_to_session(
        session_id,
        build_summary_update(
            body.content,
            new_version,
            session_id,
            summary_id=inserted_row["id"],
            analysis_run_id=_build_summary_run_id(session_id, inserted_row["window_start"]),
            window_start=inserted_row["window_start"].isoformat() if inserted_row["window_start"] else None,
            window_end=inserted_row["window_end"].isoformat() if inserted_row["window_end"] else None,
            created_at=inserted_row["created_at"].isoformat() if inserted_row["created_at"] else None,
        ),
    )

    return {"id": summary_id, "version": new_version}


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

    payload = dict(row)
    payload["analysis_run_id"] = _build_summary_run_id(payload["session_id"], payload["window_start"])
    return DiscussionSummaryOut.model_validate(payload)


@router.get(
    "/sessions/{session_id}/summaries",
    response_model=list[DiscussionSummaryOut],
)
async def list_summary_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[DiscussionSummaryOut]:
    """
    获取指定会话的全部讨论摘要历史，便于前端按分析窗口展示时间线。
    仅会话活跃成员可访问。
    """
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

    result = await db.execute(
        text(
            """
            SELECT id, session_id, version, content, window_start, window_end, created_at
            FROM discussion_summaries
            WHERE session_id = :session_id
            ORDER BY created_at DESC, version DESC
            """
        ),
        {"session_id": session_id},
    )
    rows = result.mappings().all()
    items: list[DiscussionSummaryOut] = []
    for row in rows:
        payload = dict(row)
        payload["analysis_run_id"] = _build_summary_run_id(payload["session_id"], payload["window_start"])
        items.append(DiscussionSummaryOut.model_validate(payload))
    return items
