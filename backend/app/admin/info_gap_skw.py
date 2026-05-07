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
    prefix="/api/admin/info-gap-skw",
    tags=["admin-info-gap-skw"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminKeywordSkwOut(ApiModel):
    id: str
    session_id: str
    window_start: datetime
    keyword: str
    user_a_id: str | None = None
    user_a_name: str | None = None
    user_b_id: str | None = None
    user_b_name: str | None = None
    skw_score: float | None = None
    mention_count: int | None = None
    skw_status: str | None = None
    created_at: datetime | None = None


@router.get("/", response_model=Page[AdminKeywordSkwOut])
async def list_info_gap_skw(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    keyword: str | None = None,
    user_a_id: str | None = None,
    user_b_id: str | None = None,
    skw_score_min: float | None = None,
    skw_score_max: float | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminKeywordSkwOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("ks.session_id = :session_id")
        params["session_id"] = session_id
    if keyword:
        where.append("ks.keyword ILIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if user_a_id:
        where.append("ks.user_a_id = :user_a_id")
        params["user_a_id"] = user_a_id
    if user_b_id:
        where.append("ks.user_b_id = :user_b_id")
        params["user_b_id"] = user_b_id
    if skw_score_min is not None:
        where.append("ks.skw_score >= :skw_score_min")
        params["skw_score_min"] = skw_score_min
    if skw_score_max is not None:
        where.append("ks.skw_score <= :skw_score_max")
        params["skw_score_max"] = skw_score_max
    if window_start_from:
        where.append("ks.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("ks.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM info_gap_skw ks WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                ks.id, ks.session_id, ks.window_start, ks.keyword,
                ks.user_a_id, ks.user_b_id, ks.skw_score,
                ks.mention_count, ks.skw_status, ks.created_at,
                ua.name AS user_a_name,
                ub.name AS user_b_name
            FROM info_gap_skw ks
            LEFT JOIN users_info ua ON ua.id = ks.user_a_id
            LEFT JOIN users_info ub ON ub.id = ks.user_b_id
            WHERE {where_sql}
            ORDER BY ks.window_start DESC, ks.skw_score DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminKeywordSkwOut.model_validate(dict(row)) for row in rows]

    return Page[AdminKeywordSkwOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{skw_id}", status_code=204)
async def delete_info_gap_skw(
    skw_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM info_gap_skw WHERE id = :id RETURNING id"),
        {"id": skw_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="关键词 SKW 记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_info_gap_skw(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM info_gap_skw WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
