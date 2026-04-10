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
    prefix="/api/admin/discussion-summaries",
    tags=["admin-discussion-summaries"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminDiscussionSummaryOut(BaseModel):
    id: str
    session_id: str
    session_title: str | None = None
    version: int
    content: str
    window_start: Any
    window_end: Any
    created_at: Any = None


class AdminDiscussionSummaryUpdate(BaseModel):
    content: str


@router.get("/", response_model=Page[AdminDiscussionSummaryOut])
async def list_discussion_summaries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    version: int | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminDiscussionSummaryOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("ds.session_id = :session_id")
        params["session_id"] = session_id
    if version is not None:
        where.append("ds.version = :version")
        params["version"] = version
    if window_start_from:
        where.append("ds.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("ds.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM discussion_summaries ds WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                ds.id, ds.session_id, ds.version,
                ds.content, ds.window_start, ds.window_end, ds.created_at,
                cs.session_title
            FROM discussion_summaries ds
            LEFT JOIN chat_sessions cs ON cs.id = ds.session_id
            WHERE {where_sql}
            ORDER BY ds.window_start DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminDiscussionSummaryOut.model_validate(dict(row)) for row in rows]

    return Page[AdminDiscussionSummaryOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.get("/{summary_id}", response_model=AdminDiscussionSummaryOut)
async def get_discussion_summary(
    summary_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminDiscussionSummaryOut:
    result = await db.execute(
        text(
            """
            SELECT
                ds.id, ds.session_id, ds.version,
                ds.content, ds.window_start, ds.window_end, ds.created_at,
                cs.session_title
            FROM discussion_summaries ds
            LEFT JOIN chat_sessions cs ON cs.id = ds.session_id
            WHERE ds.id = :id
            """
        ),
        {"id": summary_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="讨论摘要不存在")
    return AdminDiscussionSummaryOut.model_validate(dict(row))


@router.put("/{summary_id}", response_model=AdminDiscussionSummaryOut)
async def update_discussion_summary(
    summary_id: str,
    payload: AdminDiscussionSummaryUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminDiscussionSummaryOut:
    result = await db.execute(
        text(
            """
            UPDATE discussion_summaries
            SET content = :content
            WHERE id = :id
            RETURNING id
            """
        ),
        {"id": summary_id, "content": payload.content},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="讨论摘要不存在")
    return await get_discussion_summary(summary_id, db)


@router.delete("/{summary_id}", status_code=204)
async def delete_discussion_summary(
    summary_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM discussion_summaries WHERE id = :id RETURNING id"),
        {"id": summary_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="讨论摘要不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_discussion_summaries(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM discussion_summaries WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
