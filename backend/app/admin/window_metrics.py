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
    prefix="/api/admin/window-metrics",
    tags=["admin-window-metrics"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminWindowMetricOut(BaseModel):
    id: str
    session_id: str
    user_id: str
    user_name: str | None = None
    window_start: Any
    window_end: Any
    speaking_ratio: float | None = None
    silence_s: float | None = None
    ttr: float | None = None
    arg_density: float | None = None
    srep: float | None = None
    info_gain: float | None = None
    has_reasoning: bool | None = None
    has_evidence: bool | None = None
    created_at: Any = None


@router.get("/", response_model=Page[AdminWindowMetricOut])
async def list_window_metrics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    user_id: str | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    has_reasoning: bool | None = None,
    has_evidence: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminWindowMetricOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("wm.session_id = :session_id")
        params["session_id"] = session_id
    if user_id:
        where.append("wm.user_id = :user_id")
        params["user_id"] = user_id
    if window_start_from:
        where.append("wm.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("wm.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)
    if has_reasoning is not None:
        where.append("wm.has_reasoning = :has_reasoning")
        params["has_reasoning"] = has_reasoning
    if has_evidence is not None:
        where.append("wm.has_evidence = :has_evidence")
        params["has_evidence"] = has_evidence

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM window_metrics wm WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                wm.id, wm.session_id, wm.user_id,
                wm.window_start, wm.window_end,
                wm.speaking_ratio, wm.silence_s, wm.ttr,
                wm.arg_density, wm.srep, wm.info_gain,
                wm.has_reasoning, wm.has_evidence, wm.created_at,
                u.name AS user_name
            FROM window_metrics wm
            LEFT JOIN users_info u ON u.id = wm.user_id
            WHERE {where_sql}
            ORDER BY wm.window_start DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminWindowMetricOut.model_validate(dict(row)) for row in rows]

    return Page[AdminWindowMetricOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{metric_id}", status_code=204)
async def delete_window_metric(
    metric_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM window_metrics WHERE id = :id RETURNING id"),
        {"id": metric_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="窗口指标记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_window_metrics(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM window_metrics WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
