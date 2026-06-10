"""Admin API: 腾讯 ASR 转写文稿预处理 + CoI 编码保存。

接口列表：
  GET  /api/admin/coi-transcript-coding/sessions/{session_id}/utterance-count
  GET  /api/admin/coi-transcript-coding/sessions/{session_id}/utterances
  POST /api/admin/coi-transcript-coding/sessions/{session_id}/utterances
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin

router = APIRouter(
    prefix="/api/admin/coi-transcript-coding",
    tags=["admin-coi-transcript-coding"],
    dependencies=[Depends(require_admin)],
)

COI_CATEGORIES = {"TE", "EX", "IN", "RE"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class UtteranceCountOut(ApiModel):
    session_id: str
    group_id: str | None
    count: int


class TranscriptUtteranceIn(ApiModel):
    order_index: int
    content: str
    start_time: float | None = None   # 相对秒数，来自 TXT 时间戳
    coi_category: str | None = None   # TE/EX/IN/RE，跳过的条目传 null


class SaveTranscriptRequest(ApiModel):
    utterances: list[TranscriptUtteranceIn]


class SaveTranscriptResponse(ApiModel):
    saved: int
    deleted_previous: int


class UtteranceOut(ApiModel):
    order_index: int
    content: str
    start_time: float | None
    coi_category: str | None


class UtterancesOut(ApiModel):
    session_id: str
    group_id: str | None
    utterances: list[UtteranceOut]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_group_id(db: AsyncSession, session_id: str) -> str | None:
    result = await db.execute(
        text("SELECT group_id FROM chat_sessions WHERE id = :sid"),
        {"sid": session_id},
    )
    row = result.first()
    return str(row[0]) if row else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/utterance-count", response_model=UtteranceCountOut)
async def get_utterance_count(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> UtteranceCountOut:
    """返回该 session 当前已有的 coi_utterances 条数，用于前端显示覆盖警告。"""
    result = await db.execute(
        text("SELECT COUNT(*) FROM coi_utterances WHERE session_id = :sid"),
        {"sid": session_id},
    )
    count = result.scalar_one()
    group_id = await _get_group_id(db, session_id)
    return UtteranceCountOut(session_id=session_id, group_id=group_id, count=count)


@router.get("/sessions/{session_id}/utterances", response_model=UtterancesOut)
async def get_session_utterances(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> UtterancesOut:
    """返回该 session 已保存的话语列表（含 null category 的预处理条目）。"""
    group_id = await _get_group_id(db, session_id)
    result = await db.execute(
        text("""
            SELECT order_index, content, start_time, coi_category
            FROM coi_utterances
            WHERE session_id = :sid
            ORDER BY order_index
        """),
        {"sid": session_id},
    )
    rows = result.fetchall()
    utterances = [
        UtteranceOut(
            order_index=r[0],
            content=r[1],
            start_time=r[2],
            coi_category=r[3],
        )
        for r in rows
    ]
    return UtterancesOut(session_id=session_id, group_id=group_id, utterances=utterances)


@router.post("/sessions/{session_id}/utterances", response_model=SaveTranscriptResponse)
async def save_transcript_utterances(
    session_id: str,
    payload: SaveTranscriptRequest,
    db: AsyncSession = Depends(get_db),
) -> SaveTranscriptResponse:
    """覆盖保存：先删除该 session 全部旧数据，再批量插入。

    - 保存所有条目，coi_category 可为 null（预处理阶段）或 TE/EX/IN/RE（编码阶段）。
    - start_time 存相对秒数（ENA 分析会自动归一化）。
    """
    group_id = await _get_group_id(db, session_id)
    if not group_id:
        raise HTTPException(status_code=404, detail="会话不存在")

    to_save = payload.utterances

    # 删除旧数据
    del_result = await db.execute(
        text("DELETE FROM coi_utterances WHERE session_id = :sid RETURNING id"),
        {"sid": session_id},
    )
    deleted_previous = len(del_result.fetchall())

    # 批量插入
    if to_save:
        rows: list[dict[str, Any]] = [
            {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "group_id": group_id,
                "speaker": None,
                "speaker_name": None,
                "speaker_user_id": None,
                "content": u.content,
                "source_transcript_ids": "{}",
                "order_index": u.order_index,
                "coi_category": u.coi_category,
                "start_time": u.start_time,
            }
            for u in to_save
        ]
        await db.execute(
            text("""
                INSERT INTO coi_utterances
                    (id, session_id, group_id, speaker, speaker_name, speaker_user_id,
                     content, source_transcript_ids, order_index, coi_category, start_time)
                VALUES
                    (:id, :session_id, :group_id, :speaker, :speaker_name, :speaker_user_id,
                     :content, :source_transcript_ids::text[], :order_index, :coi_category, :start_time)
            """),
            rows,
        )

    await db.commit()
    return SaveTranscriptResponse(saved=len(to_save), deleted_previous=deleted_previous)
