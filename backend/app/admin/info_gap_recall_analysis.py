# -*- coding: utf-8 -*-
"""
关键词召回分析记录管理接口
每次关键词召回 AI 调用的原始判断，包含 needs_prompt=false 的词均入库。
"""
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
    prefix="/api/admin/info-gap-recall-analysis",
    tags=["admin-info-gap-recall-analysis"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class KeywordRecallAnalysisOut(ApiModel):
    id: str
    session_id: str
    window_start: datetime
    keyword: str
    needs_prompt: bool
    target_user_id: str | None = None
    target_user_name: str | None = None
    llm_reason: str | None = None
    created_at: datetime | None = None


@router.get("/", response_model=Page[KeywordRecallAnalysisOut])
async def list_info_gap_recall_analysis(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    keyword: str | None = None,
    needs_prompt: bool | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[KeywordRecallAnalysisOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("k.session_id = :session_id")
        params["session_id"] = session_id
    if keyword:
        where.append("k.keyword ILIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if needs_prompt is not None:
        where.append("k.needs_prompt = :needs_prompt")
        params["needs_prompt"] = needs_prompt
    if window_start_from:
        where.append("k.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("k.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM info_gap_recall_analysis k WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                k.id, k.session_id, k.window_start, k.keyword,
                k.needs_prompt, k.target_user_id,
                k.llm_reason, k.created_at,
                u.name AS target_user_name
            FROM info_gap_recall_analysis k
            LEFT JOIN users_info u ON u.id = k.target_user_id
            WHERE {where_sql}
            ORDER BY k.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [KeywordRecallAnalysisOut.model_validate(dict(row)) for row in rows]

    return Page[KeywordRecallAnalysisOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{record_id}", status_code=204)
async def delete_info_gap_recall_analysis(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM info_gap_recall_analysis WHERE id = :id RETURNING id"),
        {"id": record_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_info_gap_recall_analysis(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM info_gap_recall_analysis WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
