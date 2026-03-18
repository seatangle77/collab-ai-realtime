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
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta

router = APIRouter(
    prefix="/api/admin/push-logs",
    tags=["admin-push-logs"],
    dependencies=[Depends(require_admin)],
)

VALID_PUSH_CHANNELS = {"web", "app", "glasses"}
VALID_DELIVERY_STATUSES = {"pending", "delivered", "failed"}


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminPushLogOut(BaseModel):
    id: str
    session_id: str
    session_title: str | None = None
    state_id: str | None = None
    state_type: str | None = None
    target_user_id: str
    target_user_name: str | None = None
    push_content: str | None = None
    push_channel: str
    jpush_message_id: str | None = None
    delivery_status: str
    triggered_at: Any
    delivered_at: Any = None


class AdminPushLogCreate(BaseModel):
    session_id: str
    target_user_id: str
    push_channel: str
    state_id: str | None = None
    push_content: str | None = None
    jpush_message_id: str | None = None
    delivery_status: str = "pending"
    triggered_at: datetime | None = None
    delivered_at: datetime | None = None


@router.post(
    "/",
    response_model=AdminPushLogOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_push_log(
    payload: AdminPushLogCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminPushLogOut:
    # 枚举校验
    if payload.push_channel not in VALID_PUSH_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 push_channel，合法值：{', '.join(sorted(VALID_PUSH_CHANNELS))}",
        )
    if payload.delivery_status not in VALID_DELIVERY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 delivery_status，合法值：{', '.join(sorted(VALID_DELIVERY_STATUSES))}",
        )

    # 校验 session 存在
    r = await db.execute(
        text("SELECT id, session_title FROM chat_sessions WHERE id = :id"),
        {"id": payload.session_id},
    )
    session_row = r.mappings().first()
    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    session_title = session_row.get("session_title")

    # 校验 target_user 存在
    r2 = await db.execute(
        text("SELECT id, name FROM users_info WHERE id = :id"),
        {"id": payload.target_user_id},
    )
    user_row = r2.mappings().first()
    if not user_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户不存在")
    target_user_name = user_row.get("name")

    # 校验 state_id 存在（如果传了）
    state_type: str | None = None
    if payload.state_id:
        r3 = await db.execute(
            text("SELECT id, state_type FROM discussion_states WHERE id = :id"),
            {"id": payload.state_id},
        )
        state_row = r3.mappings().first()
        if not state_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="讨论状态记录不存在")
        state_type = state_row.get("state_type")

    log_id = f"pl{uuid.uuid4().hex[:8]}"
    triggered_at = _to_utc_naive(payload.triggered_at) if payload.triggered_at else None
    delivered_at = _to_utc_naive(payload.delivered_at) if payload.delivered_at else None

    result = await db.execute(
        text(
            """
            INSERT INTO push_logs (
                id, session_id, state_id, target_user_id,
                push_content, push_channel, jpush_message_id,
                delivery_status, triggered_at, delivered_at
            ) VALUES (
                :id, :session_id, :state_id, :target_user_id,
                :push_content, :push_channel, :jpush_message_id,
                :delivery_status,
                COALESCE(:triggered_at, NOW()),
                :delivered_at
            )
            RETURNING id, session_id, state_id, target_user_id,
                      push_content, push_channel, jpush_message_id,
                      delivery_status, triggered_at, delivered_at
            """
        ),
        {
            "id": log_id,
            "session_id": payload.session_id,
            "state_id": payload.state_id,
            "target_user_id": payload.target_user_id,
            "push_content": payload.push_content,
            "push_channel": payload.push_channel,
            "jpush_message_id": payload.jpush_message_id,
            "delivery_status": payload.delivery_status,
            "triggered_at": triggered_at,
            "delivered_at": delivered_at,
        },
    )
    await db.commit()
    row = result.mappings().one()

    return AdminPushLogOut(
        **dict(row),
        session_title=session_title,
        target_user_name=target_user_name,
        state_type=state_type,
    )


@router.get("/", response_model=Page[AdminPushLogOut])
async def list_push_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    state_id: str | None = None,
    target_user_id: str | None = None,
    push_channel: str | None = None,
    delivery_status: str | None = None,
    jpush_message_id: str | None = None,
    triggered_from: datetime | None = None,
    triggered_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminPushLogOut]:
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

    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("pl.session_id = :session_id")
        params["session_id"] = session_id
    if state_id:
        where.append("pl.state_id = :state_id")
        params["state_id"] = state_id
    if target_user_id:
        where.append("pl.target_user_id = :target_user_id")
        params["target_user_id"] = target_user_id
    if push_channel:
        where.append("pl.push_channel = :push_channel")
        params["push_channel"] = push_channel
    if delivery_status:
        where.append("pl.delivery_status = :delivery_status")
        params["delivery_status"] = delivery_status
    if jpush_message_id:
        where.append("pl.jpush_message_id = :jpush_message_id")
        params["jpush_message_id"] = jpush_message_id
    if triggered_from:
        where.append("pl.triggered_at >= :triggered_from")
        params["triggered_from"] = _to_utc_naive(triggered_from)
    if triggered_to:
        where.append("pl.triggered_at <= :triggered_to")
        params["triggered_to"] = _to_utc_naive(triggered_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM push_logs pl WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                pl.id, pl.session_id, pl.state_id,
                pl.target_user_id, pl.push_content, pl.push_channel,
                pl.jpush_message_id, pl.delivery_status,
                pl.triggered_at, pl.delivered_at,
                cs.session_title,
                u.name AS target_user_name,
                ds.state_type
            FROM push_logs pl
            LEFT JOIN chat_sessions cs ON cs.id = pl.session_id
            LEFT JOIN users_info u ON u.id = pl.target_user_id
            LEFT JOIN discussion_states ds ON ds.id = pl.state_id
            WHERE {where_sql}
            ORDER BY pl.triggered_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminPushLogOut.model_validate(dict(row)) for row in rows]

    return Page[AdminPushLogOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_push_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM push_logs WHERE id = :id RETURNING id"),
        {"id": log_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推送日志不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_push_logs(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM push_logs WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
