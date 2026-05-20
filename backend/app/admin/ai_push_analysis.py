# -*- coding: utf-8 -*-
"""
AI 推送分析记录管理接口
每次结构化推送 AI 调用的原始结果，不论是否通过过滤均入库。
drop_reason 取值：passed / needs_prompt_false / anchor_invalid / content_empty / persist_failed / session_not_ongoing
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
    prefix="/api/admin/ai-push-analysis",
    tags=["admin-ai-push-analysis"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AiPushAnalysisOut(ApiModel):
    id: str
    session_id: str
    target_user_id: str
    target_user_name: str | None = None
    state_type: str
    window_start: datetime
    ai_needs_prompt: bool
    ai_anchor: Any = None
    ai_content: str | None = None
    ai_analysis: str | None = None
    drop_reason: str | None = None
    created_at: datetime | None = None


@router.get("/", response_model=Page[AiPushAnalysisOut])
async def list_ai_push_analysis(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session_id: str | None = None,
    target_user_id: str | None = None,
    state_type: str | None = None,
    ai_needs_prompt: bool | None = None,
    drop_reason: str | None = None,
    window_start_from: datetime | None = None,
    window_start_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AiPushAnalysisOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("a.session_id = :session_id")
        params["session_id"] = session_id
    if target_user_id:
        where.append("a.target_user_id = :target_user_id")
        params["target_user_id"] = target_user_id
    if state_type:
        where.append("a.state_type = :state_type")
        params["state_type"] = state_type
    if ai_needs_prompt is not None:
        where.append("a.ai_needs_prompt = :ai_needs_prompt")
        params["ai_needs_prompt"] = ai_needs_prompt
    if drop_reason:
        where.append("a.drop_reason = :drop_reason")
        params["drop_reason"] = drop_reason
    if window_start_from:
        where.append("a.window_start >= :window_start_from")
        params["window_start_from"] = _to_utc_naive(window_start_from)
    if window_start_to:
        where.append("a.window_start <= :window_start_to")
        params["window_start_to"] = _to_utc_naive(window_start_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ai_push_analysis a WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                a.id, a.session_id, a.target_user_id,
                a.state_type, a.window_start,
                a.ai_needs_prompt, a.ai_anchor, a.ai_content, a.ai_analysis,
                a.drop_reason, a.created_at,
                u.name AS target_user_name
            FROM ai_push_analysis a
            LEFT JOIN users_info u ON u.id = a.target_user_id
            WHERE {where_sql}
            ORDER BY a.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AiPushAnalysisOut.model_validate(dict(row)) for row in rows]

    return Page[AiPushAnalysisOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{record_id}", status_code=204)
async def delete_ai_push_analysis(
    record_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM ai_push_analysis WHERE id = :id RETURNING id"),
        {"id": record_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_ai_push_analysis(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM ai_push_analysis WHERE id = ANY(:ids) RETURNING id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
