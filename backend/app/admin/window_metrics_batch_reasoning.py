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
    prefix="/api/admin/window-metrics-batch-reasoning",
    tags=["admin-window-metrics-batch-reasoning"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class WindowMetricsBatchReasoningMember(BaseModel):
    user_id: str
    reasoning_status: bool | None = None
    evidence_status: bool | None = None
    reasoning_source: str | None = None
    evidence_source: str | None = None


class WindowMetricsBatchReasoningOut(BaseModel):
    id: str
    session_id: str
    window_start: Any
    members: list[WindowMetricsBatchReasoningMember]
    created_at: Any = None


@router.get("/", response_model=Page[WindowMetricsBatchReasoningOut])
async def list_window_metrics_batch_reasoning(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[WindowMetricsBatchReasoningOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("wmbr.session_id = :session_id")
        params["session_id"] = session_id
    if window_start_from:
        where.append("wmbr.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("wmbr.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM window_metrics_batch_reasoning wmbr WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                wmbr.id,
                wmbr.session_id,
                wmbr.window_start,
                wmbr.members,
                wmbr.created_at
            FROM window_metrics_batch_reasoning wmbr
            WHERE {where_sql}
            ORDER BY wmbr.window_start DESC, wmbr.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [WindowMetricsBatchReasoningOut.model_validate(dict(row)) for row in rows]

    return Page[WindowMetricsBatchReasoningOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{record_id}", status_code=204)
async def delete_window_metrics_batch_reasoning(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM window_metrics_batch_reasoning WHERE id = :id RETURNING id"),
        {"id": record_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="窗口论证批量日志不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_window_metrics_batch_reasoning(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM window_metrics_batch_reasoning WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
