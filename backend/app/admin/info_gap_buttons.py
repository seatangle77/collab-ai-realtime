from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from ..api_model import ApiModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta

router = APIRouter(
    prefix="/api/admin/info-gap-buttons",
    tags=["admin-info-gap-buttons"],
    dependencies=[Depends(require_admin)],
)

VALID_STATUSES = {"pending", "clicked", "dismissed"}


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminInfoGapButtonOut(ApiModel):
    id: str
    session_id: str
    user_id: str
    user_name: str | None = None
    keyword: str
    skw_score: float | None = None
    status: str | None = None
    window_start: datetime
    created_at: datetime | None = None
    clicked_at: datetime | None = None


@router.get("/", response_model=Page[AdminInfoGapButtonOut])
async def list_info_gap_buttons(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    user_id: str | None = None,
    keyword: str | None = None,
    status: str | None = None,
    has_clicked: bool | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminInfoGapButtonOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("igb.session_id = :session_id")
        params["session_id"] = session_id
    if user_id:
        where.append("igb.user_id = :user_id")
        params["user_id"] = user_id
    if keyword:
        where.append("igb.keyword ILIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if status:
        where.append("igb.status = :status")
        params["status"] = status
    if has_clicked is True:
        where.append("igb.clicked_at IS NOT NULL")
    elif has_clicked is False:
        where.append("igb.clicked_at IS NULL")
    if window_start_from:
        where.append("igb.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("igb.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM info_gap_buttons igb WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                igb.id, igb.session_id, igb.user_id,
                igb.keyword, igb.skw_score, igb.status,
                igb.window_start, igb.created_at, igb.clicked_at,
                u.name AS user_name
            FROM info_gap_buttons igb
            LEFT JOIN users_info u ON u.id = igb.user_id
            WHERE {where_sql}
            ORDER BY igb.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminInfoGapButtonOut.model_validate(dict(row)) for row in rows]

    return Page[AdminInfoGapButtonOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{button_id}", status_code=204)
async def delete_info_gap_button(
    button_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM info_gap_buttons WHERE id = :id RETURNING id"),
        {"id": button_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="信息缺口按钮记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_info_gap_buttons(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM info_gap_buttons WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
