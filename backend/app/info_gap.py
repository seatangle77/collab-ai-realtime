"""
信息缺口关键词按钮接口
- GET  /api/sessions/{session_id}/info-gap/buttons  查询当前用户 pending 按钮
- POST /api/sessions/{session_id}/info-gap/click    点击按钮，更新状态
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db
from .jpush_client import send_push_to_registration_id

router = APIRouter(prefix="/api", tags=["info-gap"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class InfoGapButtonOut(BaseModel):
    id: str
    keyword: str
    skw_score: float
    status: str
    analysis_run_id: str
    window_start: Any
    created_at: Any


class ClickRequest(BaseModel):
    button_id: str


class ClickResponse(BaseModel):
    success: bool


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

@router.get(
    "/sessions/{session_id}/info-gap/buttons",
    response_model=list[InfoGapButtonOut],
)
async def get_info_gap_buttons(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[InfoGapButtonOut]:
    """查询当前用户在该会话中状态为 pending 的信息缺口关键词按钮。"""
    await _assert_session_member(session_id, current_user["id"], db)

    result = await db.execute(
        text(
            """
            SELECT id, keyword, skw_score, status, window_start, created_at
            FROM info_gap_buttons
            WHERE session_id = :session_id
              AND user_id    = :user_id
              AND status     = 'pending'
            ORDER BY created_at DESC
            """
        ),
        {"session_id": session_id, "user_id": current_user["id"]},
    )
    rows = result.mappings().all()
    items: list[InfoGapButtonOut] = []
    for row in rows:
        payload = dict(row)
        payload["analysis_run_id"] = _build_reasoning_run_id(session_id, payload["window_start"])
        items.append(InfoGapButtonOut.model_validate(payload))
    return items


@router.post(
    "/sessions/{session_id}/info-gap/click",
    response_model=ClickResponse,
)
async def click_info_gap_button(
    session_id: str,
    body: ClickRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ClickResponse:
    """
    用户点击信息缺口关键词按钮。
    - 校验按钮归属当前用户且状态为 pending
    - 更新状态为 clicked，记录 clicked_at
    - 通过 JPush 向用户设备发送提示推送（如 device_token 存在）
    - TODO Week 3：触发 AI 分析生成推送内容
    """
    await _assert_session_member(session_id, current_user["id"], db)

    # 1. 校验按钮存在且属于当前用户
    btn_result = await db.execute(
        text(
            """
            SELECT id, keyword, status
            FROM info_gap_buttons
            WHERE id         = :button_id
              AND session_id = :session_id
              AND user_id    = :user_id
            """
        ),
        {
            "button_id": body.button_id,
            "session_id": session_id,
            "user_id": current_user["id"],
        },
    )
    btn = btn_result.mappings().first()
    if not btn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="按钮不存在")
    if btn["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="按钮已被点击或已过期")

    # 2. 更新按钮状态
    # 这里避免把 Python datetime 传给 asyncpg，改用 DB NOW() 写入，
    # 防止 timestamp/timestamptz 的 naive/aware 类型不一致导致 DataError。
    await db.execute(
        text(
            """
            UPDATE info_gap_buttons
            SET status = 'clicked', clicked_at = NOW()
            WHERE id = :button_id
            """
        ),
        {"button_id": body.button_id},
    )
    await db.commit()

    # 3. 写一条 push_log 记录（push_channel = app，占位内容，Week 3 替换为 AI 生成文案）
    push_content = f"你点击了关键词「{btn['keyword']}」，AI 正在分析..."
    log_id = f"pl{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO push_logs
              (id, session_id, target_user_id, push_content,
               push_channel, delivery_status, triggered_at)
            VALUES
              (:id, :session_id, :user_id, :content,
               'app', 'pending', NOW())
            """
        ),
        {
            "id": log_id,
            "session_id": session_id,
            "user_id": current_user["id"],
            "content": push_content,
        },
    )
    await db.commit()

    # 4. JPush 推送（如果用户有 device_token）
    token_result = await db.execute(
        text("SELECT device_token FROM users_info WHERE id = :user_id"),
        {"user_id": current_user["id"]},
    )
    token_row = token_result.mappings().first()
    device_token = token_row["device_token"] if token_row else None

    if device_token:
        try:
            await asyncio.to_thread(
                send_push_to_registration_id,
                device_token,
                push_content,
                "信息缺口提示",
            )
            await db.execute(
                text(
                    "UPDATE push_logs SET delivery_status = 'delivered' WHERE id = :id"
                ),
                {"id": log_id},
            )
            await db.commit()
        except Exception:
            # 推送失败不影响接口返回，日志由 jpush_client 内部记录
            pass

    return ClickResponse(success=True)
