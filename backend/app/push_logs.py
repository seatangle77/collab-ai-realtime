from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db

router = APIRouter(prefix="/api", tags=["push-logs"])

VALID_PUSH_CHANNELS = {"web", "app", "glasses"}
VALID_DELIVERY_STATUSES = {"pending", "delivered", "failed"}


class PushLogOut(BaseModel):
    id: str
    session_id: str
    state_id: str | None = None
    push_content: str | None = None
    push_channel: str
    jpush_message_id: str | None = None
    delivery_status: str
    triggered_at: Any
    delivered_at: Any = None


@router.get(
    "/sessions/{session_id}/push-logs",
    response_model=list[PushLogOut],
)
async def get_session_push_logs(
    session_id: str,
    push_channel: str | None = Query(None),
    delivery_status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[PushLogOut]:
    """
    获取当前用户在指定会话中收到的推送日志。
    仅返回 target_user_id = 当前用户的记录。
    """
    # 枚举校验
    if push_channel is not None and push_channel not in VALID_PUSH_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 push_channel，合法值：{', '.join(sorted(VALID_PUSH_CHANNELS))}",
        )
    if delivery_status is not None and delivery_status not in VALID_DELIVERY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 delivery_status，合法值：{', '.join(sorted(VALID_DELIVERY_STATUSES))}",
        )

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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅群组成员可以查看推送日志")

    # 3. 查询当前用户的推送记录
    where: list[str] = [
        "pl.session_id = :session_id",
        "pl.target_user_id = :user_id",
    ]
    params: dict[str, Any] = {
        "session_id": session_id,
        "user_id": current_user["id"],
    }

    if push_channel is not None:
        where.append("pl.push_channel = :push_channel")
        params["push_channel"] = push_channel
    if delivery_status is not None:
        where.append("pl.delivery_status = :delivery_status")
        params["delivery_status"] = delivery_status

    where_sql = " AND ".join(where)

    result = await db.execute(
        text(
            f"""
            SELECT
                pl.id, pl.session_id, pl.state_id,
                pl.push_content, pl.push_channel,
                pl.jpush_message_id, pl.delivery_status,
                pl.triggered_at, pl.delivered_at
            FROM push_logs pl
            WHERE {where_sql}
            ORDER BY pl.triggered_at DESC
            """
        ),
        params,
    )
    rows = result.mappings().all()
    return [PushLogOut.model_validate(dict(row)) for row in rows]
