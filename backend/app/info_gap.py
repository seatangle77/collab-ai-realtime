"""
信息缺口关键词按钮接口
- GET  /api/sessions/{session_id}/info-gap/buttons  查询当前用户 pending 按钮
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, status
from .api_model import ApiModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .admin.deps import require_admin
from .auth import get_current_user
from .db import get_db
from .time_utils import utc_iso
from .ws_manager import ws_manager
from .ws_protocol import build_info_gap_button

router = APIRouter(prefix="/api", tags=["info-gap"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class InfoGapButtonOut(ApiModel):
    id: str
    keyword: str
    skw_score: float
    status: str
    analysis_run_id: str
    window_start: datetime
    created_at: datetime


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _build_reasoning_run_id(session_id: str, window_start: Any) -> str:
    value = window_start.isoformat() if hasattr(window_start, "isoformat") else str(window_start)
    return f"reasoning:{session_id}:{value}"

async def _assert_session_member(
    session_id: str,
    user_id: str,
    db: AsyncSession,
) -> None:
    """校验会话存在且当前用户是活跃成员，否则抛 HTTPException。"""
    row = await db.execute(
        text(
            """
            SELECT 1 FROM chat_sessions cs
            JOIN group_memberships gm ON gm.group_id = cs.group_id
            WHERE cs.id = :session_id
              AND gm.user_id = :user_id
              AND gm.status = 'active'
            """
        ),
        {"session_id": session_id, "user_id": user_id},
    )
    if not row.first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅会话活跃成员可访问",
        )


# ── 接口 ──────────────────────────────────────────────────────────────────────

class InfoGapNotifyIn(ApiModel):
    user_id: str
    button_id: str
    keyword: str
    skw_score: float
    window_start: str  # ISO 8601


@router.post(
    "/internal/sessions/{session_id}/info-gap/notify",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def notify_info_gap_button(
    session_id: str,
    body: InfoGapNotifyIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Agent 写完 info_gap_buttons 后调此接口，把新按钮通过 WebSocket 推给目标用户。
    """
    analysis_run_id = _build_reasoning_run_id(session_id, body.window_start)

    # 读取 created_at（让前端时间轴能用）
    result = await db.execute(
        text("SELECT created_at FROM info_gap_buttons WHERE id = :id"),
        {"id": body.button_id},
    )
    row = result.mappings().first()
    created_at = utc_iso(row["created_at"]) if row else None

    button_payload = {
        "id": body.button_id,
        "keyword": body.keyword,
        "skw_score": body.skw_score,
        "analysis_run_id": analysis_run_id,
        "window_start": body.window_start,
        "created_at": created_at,
    }

    sent = await ws_manager.send_to_user(
        session_id,
        body.user_id,
        build_info_gap_button([button_payload]),
    )

    return {"sent": sent, "button_id": body.button_id}


@router.get(
    "/sessions/{session_id}/info-gap/buttons",
    response_model=list[InfoGapButtonOut],
)
async def get_info_gap_buttons(
    session_id: str,
    include_all: bool = Query(False, description="是否返回当前用户该会话下的全部关键词按钮状态"),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[InfoGapButtonOut]:
    """查询当前用户在该会话中的信息缺口关键词按钮，默认仅返回 pending。"""
    await _assert_session_member(session_id, current_user["id"], db)

    query_sql = """
            SELECT id, keyword, skw_score, status, window_start, created_at
            FROM info_gap_buttons
            WHERE session_id = :session_id
              AND user_id    = :user_id
    """
    if include_all:
        query_sql += "\n              AND status IN ('pending', 'clicked')"
    else:
        query_sql += "\n              AND status     = 'pending'"
    query_sql += "\n            ORDER BY created_at DESC"

    result = await db.execute(
        text(query_sql),
        {"session_id": session_id, "user_id": current_user["id"]},
    )
    rows = result.mappings().all()
    items: list[InfoGapButtonOut] = []
    for row in rows:
        payload = dict(row)
        payload["analysis_run_id"] = _build_reasoning_run_id(session_id, payload["window_start"])
        items.append(InfoGapButtonOut.model_validate(payload))
    return items
