from __future__ import annotations

from typing import Any
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..groups import _get_group_or_404
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(prefix="/api/admin/chat-sessions", tags=["admin-chat-sessions"])


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminChatSessionOut(BaseModel):
    id: str
    group_id: str
    session_title: str
    created_at: Any
    last_updated: Any
    is_active: bool | None = None
    ended_at: datetime | None = None


class AdminChatSessionUpdate(BaseModel):
    session_title: str | None = None
    is_active: bool | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    last_updated: datetime | None = None


class AdminChatSessionCreate(BaseModel):
    group_id: str
    session_title: str
    is_active: bool | None = None
    created_at: datetime | None = None
    last_updated: datetime | None = None
    ended_at: datetime | None = None


@router.get(
    "/",
    response_model=Page[AdminChatSessionOut],
    dependencies=[Depends(require_admin)],
)
async def list_chat_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    group_id: str | None = None,
    is_active: bool | None = None,
    status_param: str | None = Query(
        default=None,
        alias="status",
        description="会话状态：not_started / ongoing / ended；若提供，则优先于 is_active 筛选",
    ),
    title: str | None = Query(default=None, alias="session_title"),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    last_updated_from: datetime | None = None,
    last_updated_to: datetime | None = None,
    ended_from: datetime | None = None,
    ended_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminChatSessionOut]:
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}

    if group_id:
        where_clauses.append("group_id = :group_id")
        params["group_id"] = group_id

    # 状态优先：若显式传入 status（status_param），则按照 not_started/ongoing/ended 三态进行筛选；
    # 否则回退到原有的 is_active 布尔筛选逻辑。
    if status_param is not None:
        # not_started: 认为是尚未有任何更新/结束的会话，使用 created_at == last_updated 且尚未结束 近似 表示
        if status_param == "not_started":
            where_clauses.append("ended_at IS NULL AND created_at = last_updated")
        # ongoing: 认为是已经有过更新但尚未结束的会话
        elif status_param == "ongoing":
            where_clauses.append("ended_at IS NULL AND created_at <> last_updated")
        # ended: 结束时间非空即视为已结束
        elif status_param == "ended":
            where_clauses.append("ended_at IS NOT NULL")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的会话状态",
            )
    elif is_active is not None:
        where_clauses.append("is_active = :is_active")
        params["is_active"] = is_active
    if title:
        where_clauses.append("session_title ILIKE :title")
        params["title"] = f"%{title}%"
    if created_from:
        where_clauses.append("created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where_clauses.append("created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)
    if last_updated_from:
        where_clauses.append("last_updated >= :last_updated_from")
        params["last_updated_from"] = _to_utc_naive(last_updated_from)
    if last_updated_to:
        where_clauses.append("last_updated <= :last_updated_to")
        params["last_updated_to"] = _to_utc_naive(last_updated_to)
    if ended_from:
        where_clauses.append("ended_at >= :ended_from")
        params["ended_from"] = _to_utc_naive(ended_from)
    if ended_to:
        where_clauses.append("ended_at <= :ended_to")
        params["ended_to"] = _to_utc_naive(ended_to)

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM chat_sessions WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    query = text(
        f"""
        SELECT id, group_id, session_title, created_at, last_updated, is_active, ended_at
        FROM chat_sessions
        WHERE {where_sql}
        ORDER BY last_updated DESC, created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    params_with_page = dict(params)
    params_with_page["limit"] = page_size
    params_with_page["offset"] = offset

    result = await db.execute(query, params_with_page)
    rows = result.mappings().all()
    items = [AdminChatSessionOut.model_validate(dict(row)) for row in rows]

    return Page[AdminChatSessionOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.post(
    "/",
    response_model=AdminChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_chat_session(
    payload: AdminChatSessionCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminChatSessionOut:
    # 校验群组存在且处于可用状态（使用业务侧的 _get_group_or_404，要求 is_active = TRUE）
    await _get_group_or_404(payload.group_id, db)

    session_id = f"s{uuid.uuid4().hex[:8]}"

    # 计算各时间字段：
    # - 若未显式传入，则沿用原有行为，使用当前时间；
    # - 若传入，则统一转为 UTC naive 后写入。
    now_utc = datetime.now(timezone.utc)
    created_at = payload.created_at or now_utc
    last_updated = payload.last_updated or created_at
    ended_at = payload.ended_at

    created_at_naive = _to_utc_naive(created_at)
    last_updated_naive = _to_utc_naive(last_updated)
    ended_at_naive = _to_utc_naive(ended_at) if ended_at is not None else None

    # 数据库中 is_active 为 NOT NULL，且业务侧 create_session 默认视为可用会话。
    # 若传入 ended_at 且未显式指定 is_active，则默认视为已结束会话。
    if payload.is_active is None:
        is_active_value = False if ended_at is not None else True
    else:
        is_active_value = payload.is_active

    result = await db.execute(
        text(
            """
            INSERT INTO chat_sessions (id, group_id, session_title, created_at, last_updated, is_active, ended_at)
            VALUES (:id, :group_id, :title, :created_at, :last_updated, :is_active, :ended_at)
            RETURNING id, group_id, session_title, created_at, last_updated, is_active, ended_at
            """
        ),
        {
            "id": session_id,
            "group_id": payload.group_id,
            "title": payload.session_title,
            "is_active": is_active_value,
            "created_at": created_at_naive,
            "last_updated": last_updated_naive,
            "ended_at": ended_at_naive,
        },
    )
    row = result.mappings().first()
    await db.commit()

    return AdminChatSessionOut.model_validate(dict(row))


@router.get(
    "/{session_id}",
    response_model=AdminChatSessionOut,
    dependencies=[Depends(require_admin)],
)
async def get_chat_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminChatSessionOut:
    result = await db.execute(
        text(
            """
            SELECT id, group_id, session_title, created_at, last_updated, is_active, ended_at
            FROM chat_sessions
            WHERE id = :id
            """
        ),
        {"id": session_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    return AdminChatSessionOut.model_validate(dict(row))


@router.patch(
    "/{session_id}",
    response_model=AdminChatSessionOut,
    dependencies=[Depends(require_admin)],
)
async def update_chat_session(
    session_id: str,
    payload: AdminChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminChatSessionOut:
    if (
        payload.session_title is None
        and payload.is_active is None
        and payload.ended_at is None
        and payload.created_at is None
        and payload.last_updated is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有任何可更新字段",
        )

    sets: list[str] = []
    params: dict[str, Any] = {"id": session_id}

    if payload.session_title is not None:
        sets.append("session_title = :title")
        params["title"] = payload.session_title
    if payload.is_active is not None:
        sets.append("is_active = :is_active")
        params["is_active"] = payload.is_active
    if payload.ended_at is not None:
        sets.append("ended_at = :ended_at")
        params["ended_at"] = _to_utc_naive(payload.ended_at)
    if payload.created_at is not None:
        sets.append("created_at = :created_at")
        params["created_at"] = _to_utc_naive(payload.created_at)

    # last_updated：若调用方显式传入，则使用传入值；否则保持原有行为，自动刷新为当前时间。
    if payload.last_updated is not None:
        sets.append("last_updated = :last_updated")
        params["last_updated"] = _to_utc_naive(payload.last_updated)
    else:
        sets.append("last_updated = NOW()")

    set_sql = ", ".join(sets)

    result = await db.execute(
        text(
            f"""
            UPDATE chat_sessions
            SET {set_sql}
            WHERE id = :id
            RETURNING id, group_id, session_title, created_at, last_updated, is_active, ended_at
            """
        ),
        params,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    await db.commit()
    return AdminChatSessionOut.model_validate(dict(row))


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM chat_sessions WHERE id = :id"),
        {"id": session_id},
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    await db.commit()

