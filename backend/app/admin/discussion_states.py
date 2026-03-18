from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta

router = APIRouter(
    prefix="/api/admin/discussion-states",
    tags=["admin-discussion-states"],
    dependencies=[Depends(require_admin)],
)

VALID_STATE_TYPES = {
    "low_participation", "over_dominance", "disengaged",
    "deadlock", "topic_drift", "low_depth", "homogeneous",
}


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminDiscussionStateOut(BaseModel):
    id: str
    session_id: str
    triggered_at: Any
    state_type: str
    target_user_id: str | None = None
    target_user_name: str | None = None
    trigger_metrics: dict | None = None
    ai_analysis_done: bool
    push_sent: bool


class AdminDiscussionStateCreate(BaseModel):
    session_id: str
    state_type: str
    target_user_id: str | None = None
    trigger_metrics: dict | None = None
    ai_analysis_done: bool = False
    push_sent: bool = False
    triggered_at: datetime | None = None


@router.post(
    "/",
    response_model=AdminDiscussionStateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_discussion_state(
    payload: AdminDiscussionStateCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminDiscussionStateOut:
    if payload.state_type not in VALID_STATE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 state_type，合法值：{', '.join(sorted(VALID_STATE_TYPES))}",
        )

    # 校验 session 存在
    r = await db.execute(
        text("SELECT id FROM chat_sessions WHERE id = :id"),
        {"id": payload.session_id},
    )
    if not r.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 校验 target_user 存在（如果传了）
    target_user_name: str | None = None
    if payload.target_user_id:
        r2 = await db.execute(
            text("SELECT id, name FROM users_info WHERE id = :id"),
            {"id": payload.target_user_id},
        )
        user_row = r2.mappings().first()
        if not user_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户不存在")
        target_user_name = user_row.get("name")

    state_id = f"ds{uuid.uuid4().hex[:8]}"
    triggered_at = _to_utc_naive(payload.triggered_at) if payload.triggered_at else None
    trigger_metrics_json = json.dumps(payload.trigger_metrics) if payload.trigger_metrics else None

    result = await db.execute(
        text(
            """
            INSERT INTO discussion_states (
                id, session_id, state_type, target_user_id,
                trigger_metrics, ai_analysis_done, push_sent, triggered_at
            ) VALUES (
                :id, :session_id, :state_type, :target_user_id,
                CAST(:trigger_metrics AS jsonb),
                :ai_analysis_done, :push_sent,
                COALESCE(:triggered_at, NOW())
            )
            RETURNING id, session_id, triggered_at, state_type,
                      target_user_id, trigger_metrics, ai_analysis_done, push_sent
            """
        ),
        {
            "id": state_id,
            "session_id": payload.session_id,
            "state_type": payload.state_type,
            "target_user_id": payload.target_user_id,
            "trigger_metrics": trigger_metrics_json,
            "ai_analysis_done": payload.ai_analysis_done,
            "push_sent": payload.push_sent,
            "triggered_at": triggered_at,
        },
    )
    await db.commit()
    row = result.mappings().one()

    trigger_metrics_out = row.get("trigger_metrics")
    if isinstance(trigger_metrics_out, str):
        try:
            trigger_metrics_out = json.loads(trigger_metrics_out)
        except Exception:
            trigger_metrics_out = None

    return AdminDiscussionStateOut(
        id=row["id"],
        session_id=row["session_id"],
        triggered_at=row["triggered_at"],
        state_type=row["state_type"],
        target_user_id=row.get("target_user_id"),
        target_user_name=target_user_name,
        trigger_metrics=trigger_metrics_out,
        ai_analysis_done=row["ai_analysis_done"],
        push_sent=row["push_sent"],
    )


@router.get("/", response_model=Page[AdminDiscussionStateOut])
async def list_discussion_states(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    state_type: str | None = None,
    target_user_id: str | None = None,
    ai_analysis_done: bool | None = None,
    push_sent: bool | None = None,
    triggered_from: datetime | None = None,
    triggered_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminDiscussionStateOut]:
    if state_type is not None and state_type not in VALID_STATE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 state_type，合法值：{', '.join(sorted(VALID_STATE_TYPES))}",
        )

    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("ds.session_id = :session_id")
        params["session_id"] = session_id
    if state_type:
        where.append("ds.state_type = :state_type")
        params["state_type"] = state_type
    if target_user_id:
        where.append("ds.target_user_id = :target_user_id")
        params["target_user_id"] = target_user_id
    if ai_analysis_done is not None:
        where.append("ds.ai_analysis_done = :ai_analysis_done")
        params["ai_analysis_done"] = ai_analysis_done
    if push_sent is not None:
        where.append("ds.push_sent = :push_sent")
        params["push_sent"] = push_sent
    if triggered_from:
        where.append("ds.triggered_at >= :triggered_from")
        params["triggered_from"] = _to_utc_naive(triggered_from)
    if triggered_to:
        where.append("ds.triggered_at <= :triggered_to")
        params["triggered_to"] = _to_utc_naive(triggered_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM discussion_states ds WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                ds.id, ds.session_id, ds.triggered_at, ds.state_type,
                ds.target_user_id, ds.trigger_metrics,
                ds.ai_analysis_done, ds.push_sent,
                u.name AS target_user_name
            FROM discussion_states ds
            LEFT JOIN users_info u ON u.id = ds.target_user_id
            WHERE {where_sql}
            ORDER BY ds.triggered_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()

    items: list[AdminDiscussionStateOut] = []
    for row in rows:
        trigger_metrics = row.get("trigger_metrics")
        if isinstance(trigger_metrics, str):
            try:
                trigger_metrics = json.loads(trigger_metrics)
            except Exception:
                trigger_metrics = None

        items.append(
            AdminDiscussionStateOut(
                id=row["id"],
                session_id=row["session_id"],
                triggered_at=row["triggered_at"],
                state_type=row["state_type"],
                target_user_id=row.get("target_user_id"),
                target_user_name=row.get("target_user_name"),
                trigger_metrics=trigger_metrics,
                ai_analysis_done=row["ai_analysis_done"],
                push_sent=row["push_sent"],
            )
        )

    return Page[AdminDiscussionStateOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )
