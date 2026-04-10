from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta

router = APIRouter(
    prefix="/api/admin/session-text-messages",
    tags=["admin-session-text-messages"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminSessionTextMessageOut(BaseModel):
    id: str
    group_id: str
    session_id: str
    user_id: str | None = None
    user_name: str | None = None
    sender_name: str | None = None
    content: str | None = None
    created_at: Any = None


@router.get("/", response_model=Page[AdminSessionTextMessageOut])
async def list_session_text_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    group_id: str | None = None,
    user_id: str | None = None,
    sender_name: str | None = None,
    content: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminSessionTextMessageOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("stm.session_id = :session_id")
        params["session_id"] = session_id
    if group_id:
        where.append("stm.group_id = :group_id")
        params["group_id"] = group_id
    if user_id:
        where.append("stm.user_id = :user_id")
        params["user_id"] = user_id
    if sender_name:
        where.append("stm.sender_name ILIKE :sender_name")
        params["sender_name"] = f"%{sender_name}%"
    if content:
        where.append("stm.content ILIKE :content")
        params["content"] = f"%{content}%"
    if created_from:
        where.append("stm.created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where.append("stm.created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM session_text_messages stm WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                stm.id, stm.group_id, stm.session_id,
                stm.user_id, stm.sender_name, stm.content, stm.created_at,
                u.name AS user_name
            FROM session_text_messages stm
            LEFT JOIN users_info u ON u.id = stm.user_id
            WHERE {where_sql}
            ORDER BY stm.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminSessionTextMessageOut.model_validate(dict(row)) for row in rows]

    return Page[AdminSessionTextMessageOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{message_id}", status_code=204)
async def delete_session_text_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM session_text_messages WHERE id = :id RETURNING id"),
        {"id": message_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="文字消息记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_session_text_messages(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM session_text_messages WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
