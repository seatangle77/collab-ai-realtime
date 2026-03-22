from __future__ import annotations

from typing import Any
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from .deps import require_admin
from .schemas import BatchDeleteRequest, BatchDeleteResponse, Page, PageMeta


router = APIRouter(prefix="/api/admin/transcripts", tags=["admin-transcripts"])


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminTranscriptOut(BaseModel):
    transcript_id: str
    group_id: str
    session_id: str
    user_id: str | None = None
    speaker: str | None = None
    text: str | None = None
    start: Any
    end: Any
    duration: float | None = None
    confidence: float | None = None
    created_at: Any
    audio_url: str | None = None
    original_text: str | None = None
    is_edited: bool = False


class AdminTranscriptCreate(BaseModel):
    session_id: str
    group_id: str
    text: str | None = None
    start: datetime
    end: datetime
    user_id: str | None = None
    speaker: str | None = None
    duration: float | None = None
    confidence: float | None = None
    audio_url: str | None = None


class AdminTranscriptUpdate(BaseModel):
    text: str


# ── 创建（测试 / 管理用途）──────────────────────────────────────────────────

@router.post(
    "/",
    response_model=AdminTranscriptOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_transcript(
    payload: AdminTranscriptCreate,
    db: AsyncSession = Depends(get_db),
) -> AdminTranscriptOut:
    # 校验 session 存在
    sess = await db.execute(
        text("SELECT id FROM chat_sessions WHERE id = :id"),
        {"id": payload.session_id},
    )
    if not sess.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    # 校验 group 存在
    grp = await db.execute(
        text("SELECT id FROM groups WHERE id = :id"),
        {"id": payload.group_id},
    )
    if not grp.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群组不存在")

    tid = f"tr{uuid.uuid4().hex[:8]}"

    result = await db.execute(
        text(
            """
            INSERT INTO speech_transcripts
                (transcript_id, session_id, group_id, user_id, speaker, text,
                 start, "end", duration, confidence, audio_url, created_at)
            VALUES
                (:tid, :session_id, :group_id, :user_id, :speaker, :text,
                 :start, :end, :duration, :confidence, :audio_url, NOW())
            RETURNING
                transcript_id, group_id, session_id, user_id, speaker, text,
                start, "end", duration, confidence, created_at,
                audio_url, original_text, is_edited
            """
        ),
        {
            "tid": tid,
            "session_id": payload.session_id,
            "group_id": payload.group_id,
            "user_id": payload.user_id,
            "speaker": payload.speaker,
            "text": payload.text,
            "start": _to_utc_naive(payload.start),
            "end": _to_utc_naive(payload.end),
            "duration": payload.duration,
            "confidence": payload.confidence,
            "audio_url": payload.audio_url,
        },
    )
    await db.commit()
    row = result.mappings().one()
    payload_dict = dict(row)

    # 广播给所有连接该 session 的 WS 客户端
    from ..ws_sessions import broadcast_transcript
    from ..transcript_realtime import _row_to_ws_payload
    await broadcast_transcript(payload.session_id, _row_to_ws_payload(payload_dict))

    return AdminTranscriptOut.model_validate(payload_dict)


# ── 列表 ────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=Page[AdminTranscriptOut],
    dependencies=[Depends(require_admin)],
)
async def list_transcripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    group_id: str | None = None,
    speaker_user_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminTranscriptOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("t.session_id = :session_id")
        params["session_id"] = session_id
    if group_id:
        where.append("t.group_id = :group_id")
        params["group_id"] = group_id
    if speaker_user_id:
        where.append("t.user_id = :speaker_user_id")
        params["speaker_user_id"] = speaker_user_id
    if created_from:
        where.append("t.created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where.append("t.created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)

    where_sql = " AND ".join(where)

    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM speech_transcripts t WHERE {where_sql}"),
            params,
        )
    ).scalar_one()

    rows = (
        await db.execute(
            text(
                f"""
                SELECT
                    transcript_id, group_id, session_id, user_id, speaker, text,
                    start, "end", duration, confidence, created_at,
                    audio_url, original_text, is_edited
                FROM speech_transcripts t
                WHERE {where_sql}
                ORDER BY start ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": page_size, "offset": offset},
        )
    ).mappings().all()

    return Page[AdminTranscriptOut](
        items=[AdminTranscriptOut.model_validate(dict(r)) for r in rows],
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


# ── 修正文本 ─────────────────────────────────────────────────────────────────

@router.patch(
    "/{transcript_id}",
    response_model=AdminTranscriptOut,
    dependencies=[Depends(require_admin)],
)
async def update_transcript(
    transcript_id: str,
    payload: AdminTranscriptUpdate,
    db: AsyncSession = Depends(get_db),
) -> AdminTranscriptOut:
    result = await db.execute(
        text(
            """
            UPDATE speech_transcripts
            SET
                original_text = CASE WHEN is_edited = false THEN text ELSE original_text END,
                text = :new_text,
                is_edited = true
            WHERE transcript_id = :tid
            RETURNING
                transcript_id, group_id, session_id, user_id, speaker, text,
                start, "end", duration, confidence, created_at,
                audio_url, original_text, is_edited
            """
        ),
        {"tid": transcript_id, "new_text": payload.text},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    await db.commit()
    return AdminTranscriptOut.model_validate(dict(row))


# ── 删除单条 ─────────────────────────────────────────────────────────────────

@router.delete(
    "/{transcript_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_transcript(
    transcript_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM speech_transcripts WHERE transcript_id = :tid"),
        {"tid": transcript_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    await db.commit()


# ── 批量删除 ─────────────────────────────────────────────────────────────────

@router.post(
    "/batch-delete",
    response_model=BatchDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def batch_delete_transcripts(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    deleted = 0
    for tid in body.ids:
        result = await db.execute(
            text("DELETE FROM speech_transcripts WHERE transcript_id = :tid"),
            {"tid": tid},
        )
        deleted += result.rowcount
    await db.commit()
    return BatchDeleteResponse(deleted=deleted)
