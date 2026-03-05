from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
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
    if is_active is not None:
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
        params["ended_at"] = payload.ended_at

    # 每次更新顺带刷新 last_updated
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

