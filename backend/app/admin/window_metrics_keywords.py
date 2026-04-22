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
    prefix="/api/admin/window-metrics-keywords",
    tags=["admin-window-metrics-keywords"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminWindowMetricsKeywordOut(BaseModel):
    id: str
    session_id: str
    window_start: Any
    keyword: str
    created_at: Any = None


@router.get("/", response_model=Page[AdminWindowMetricsKeywordOut])
async def list_window_metrics_keywords(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    keyword: str | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminWindowMetricsKeywordOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("wmk.session_id = :session_id")
        params["session_id"] = session_id
    if keyword:
        where.append("wmk.keyword ILIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if window_start_from:
        where.append("wmk.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("wmk.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM window_metrics_keywords wmk WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                wmk.id,
                wmk.session_id,
                wmk.window_start,
                wmk.keyword,
                wmk.created_at
            FROM window_metrics_keywords wmk
            WHERE {where_sql}
            ORDER BY wmk.window_start DESC, wmk.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminWindowMetricsKeywordOut.model_validate(dict(row)) for row in rows]

    return Page[AdminWindowMetricsKeywordOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{keyword_id}", status_code=204)
async def delete_window_metrics_keyword(
    keyword_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM window_metrics_keywords WHERE id = :id RETURNING id"),
        {"id": keyword_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="窗口关键词记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_window_metrics_keywords(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM window_metrics_keywords WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
