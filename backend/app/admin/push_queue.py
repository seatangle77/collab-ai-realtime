from __future__ import annotations

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
    prefix="/api/admin/push-queue",
    tags=["admin-push-queue"],
    dependencies=[Depends(require_admin)],
)

VALID_STATE_TYPES = {
    "stagnation", "shallow", "none",
    "low_participation", "over_dominance", "disengaged",
    "deadlock", "topic_drift", "low_depth", "homogeneous",
}

VALID_STATUSES = {"pending", "processing", "delivered", "skipped", "failed", "deferred"}


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminPushQueueOut(BaseModel):
    id: str
    session_id: str
    session_title: str | None = None
    target_user_id: str
    target_user_name: str | None = None
    state_type: str
    push_content: str
    analysis_window_start: Any
    status: str
    created_at: Any
    delivered_at: Any = None


@router.get("/", response_model=Page[AdminPushQueueOut])
async def list_push_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    target_user_id: str | None = None,
    state_type: str | None = None,
    status: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminPushQueueOut]:
    if state_type is not None and state_type not in VALID_STATE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 state_type，合法值：{', '.join(sorted(VALID_STATE_TYPES))}",
        )
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 status，合法值：{', '.join(sorted(VALID_STATUSES))}",
        )

    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("pq.session_id = :session_id")
        params["session_id"] = session_id
    if target_user_id:
        where.append("pq.target_user_id = :target_user_id")
        params["target_user_id"] = target_user_id
    if state_type:
        where.append("pq.state_type = :state_type")
        params["state_type"] = state_type
    if status:
        where.append("pq.status = :status")
        params["status"] = status
    if created_from:
        where.append("pq.created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where.append("pq.created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM push_queue pq WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                pq.id, pq.session_id, pq.target_user_id,
                pq.state_type, pq.push_content,
                pq.analysis_window_start, pq.status,
                pq.created_at, pq.delivered_at,
                cs.session_title,
                u.name AS target_user_name
            FROM push_queue pq
            LEFT JOIN chat_sessions cs ON cs.id = pq.session_id
            LEFT JOIN users_info u ON u.id = pq.target_user_id
            WHERE {where_sql}
            ORDER BY pq.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminPushQueueOut.model_validate(dict(row)) for row in rows]

    return Page[AdminPushQueueOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{queue_id}", status_code=204)
async def delete_push_queue_item(
    queue_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM push_queue WHERE id = :id RETURNING id"),
        {"id": queue_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="推送队列记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_push_queue(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM push_queue WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
