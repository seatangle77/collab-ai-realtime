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
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta


router = APIRouter(prefix="/api/admin/chat-sessions", tags=["admin-chat-sessions"])


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminChatSessionOut(BaseModel):
    id: str
    group_id: str
    group_name: str | None = None
    session_title: str
    created_at: Any
    last_updated: Any
    status: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AdminChatSessionUpdate(BaseModel):
    session_title: str | None = None
    status: str | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    last_updated: datetime | None = None


class AdminChatSessionCreate(BaseModel):
    group_id: str
    session_title: str
    status: str | None = None
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
    status_param: str | None = Query(
        default=None,
        alias="status",
        description="会话状态：not_started / ongoing / ended",
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
        where_clauses.append("cs.group_id = :group_id")
        params["group_id"] = group_id

    if status_param is not None:
        if status_param in ("not_started", "ongoing", "ended"):
            where_clauses.append("cs.status = :status_param")
            params["status_param"] = status_param
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的会话状态",
            )

    if title:
        where_clauses.append("cs.session_title ILIKE :title")
        params["title"] = f"%{title}%"
    if created_from:
        where_clauses.append("cs.created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where_clauses.append("cs.created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)
    if last_updated_from:
        where_clauses.append("cs.last_updated >= :last_updated_from")
        params["last_updated_from"] = _to_utc_naive(last_updated_from)
    if last_updated_to:
        where_clauses.append("cs.last_updated <= :last_updated_to")
        params["last_updated_to"] = _to_utc_naive(last_updated_to)
    if ended_from:
        where_clauses.append("cs.ended_at >= :ended_from")
        params["ended_from"] = _to_utc_naive(ended_from)
    if ended_to:
        where_clauses.append("cs.ended_at <= :ended_to")
        params["ended_to"] = _to_utc_naive(ended_to)

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM chat_sessions cs WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    query = text(
        f"""
        SELECT
            cs.id,
            cs.group_id,
            cs.session_title,
            cs.created_at,
            cs.last_updated,
            cs.status,
            cs.started_at,
            cs.ended_at,
            g.name AS group_name
        FROM chat_sessions cs
        JOIN groups g ON g.id = cs.group_id
        WHERE {where_sql}
        ORDER BY cs.last_updated DESC, cs.created_at DESC
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
    await _get_group_or_404(payload.group_id, db)

    session_id = f"s{uuid.uuid4().hex[:8]}"

    now_utc = datetime.now(timezone.utc)
    created_at = payload.created_at or now_utc
    last_updated = payload.last_updated or created_at
    ended_at = payload.ended_at

    created_at_naive = _to_utc_naive(created_at)
    last_updated_naive = _to_utc_naive(last_updated)
    ended_at_naive = _to_utc_naive(ended_at) if ended_at is not None else None

    if payload.status is not None:
        session_status = payload.status
    elif ended_at is not None:
        session_status = "ended"
    else:
        session_status = "not_started"

    result = await db.execute(
        text(
            """
            INSERT INTO chat_sessions (id, group_id, session_title, created_at, last_updated, status, ended_at)
            VALUES (:id, :group_id, :title, :created_at, :last_updated, :status, :ended_at)
            RETURNING id, group_id, session_title, created_at, last_updated, status, started_at, ended_at
            """
        ),
        {
            "id": session_id,
            "group_id": payload.group_id,
            "title": payload.session_title,
            "status": session_status,
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
            SELECT id, group_id, session_title, created_at, last_updated, status, started_at, ended_at
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
        and payload.status is None
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
    if payload.status is not None:
        sets.append("status = :status")
        params["status"] = payload.status
    if payload.ended_at is not None:
        sets.append("ended_at = :ended_at")
        params["ended_at"] = _to_utc_naive(payload.ended_at)
    if payload.created_at is not None:
        sets.append("created_at = :created_at")
        params["created_at"] = _to_utc_naive(payload.created_at)

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
            RETURNING id, group_id, session_title, created_at, last_updated, status, started_at, ended_at
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


@router.post(
    "/batch-delete",
    response_model=BatchDeleteResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def batch_delete_chat_sessions(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    deleted = 0
    for sid in body.ids:
        result = await db.execute(
            text("DELETE FROM chat_sessions WHERE id = :id"),
            {"id": sid},
        )
        deleted += result.rowcount
    await db.commit()
    return BatchDeleteResponse(deleted=deleted)
