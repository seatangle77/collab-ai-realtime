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
    prefix="/api/admin/speech-transcripts",
    tags=["admin-speech-transcripts"],
    dependencies=[Depends(require_admin)],
)


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class AdminSpeechTranscriptOut(BaseModel):
    transcript_id: str
    group_id: str
    session_id: str
    user_id: str | None = None
    speaker: str | None = None
    text: str | None = None
    start: Any = None
    end: Any = None
    duration: float | None = None
    created_at: Any = None
    audio_url: str | None = None
    confidence: float | None = None
    speaker_confidence: float | None = None
    speaker_user_id: str | None = None
    original_text: str | None = None
    is_edited: bool


@router.get("/", response_model=Page[AdminSpeechTranscriptOut])
async def list_speech_transcripts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: str | None = None,
    group_id: str | None = None,
    speaker: str | None = None,
    text_keyword: str | None = Query(None, alias="text"),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminSpeechTranscriptOut]:
    offset = (page - 1) * page_size
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if session_id:
        where.append("t.session_id = :session_id")
        params["session_id"] = session_id
    if group_id:
        where.append("t.group_id = :group_id")
        params["group_id"] = group_id
    if speaker:
        where.append("t.speaker ILIKE :speaker")
        params["speaker"] = f"%{speaker}%"
    if text_keyword:
        where.append("t.text ILIKE :text_keyword")
        params["text_keyword"] = f"%{text_keyword}%"
    if created_from:
        where.append("t.created_at >= :created_from")
        params["created_from"] = _to_utc_naive(created_from)
    if created_to:
        where.append("t.created_at <= :created_to")
        params["created_to"] = _to_utc_naive(created_to)

    where_sql = " AND ".join(where)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM speech_transcripts t WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            f"""
            SELECT
                t.transcript_id,
                t.group_id,
                t.session_id,
                t.user_id,
                t.speaker,
                t.text,
                t.start,
                t."end" AS "end",
                t.duration,
                t.created_at,
                t.audio_url,
                t.confidence,
                t.speaker_confidence,
                t.speaker_user_id,
                t.original_text,
                t.is_edited
            FROM speech_transcripts t
            WHERE {where_sql}
            ORDER BY t.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = result.mappings().all()
    items = [AdminSpeechTranscriptOut.model_validate(dict(row)) for row in rows]

    return Page[AdminSpeechTranscriptOut](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.delete("/{transcript_id}", status_code=204)
async def delete_speech_transcript(
    transcript_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text("DELETE FROM speech_transcripts WHERE transcript_id = :transcript_id RETURNING transcript_id"),
        {"transcript_id": transcript_id},
    )
    await db.commit()
    if not result.first():
        raise HTTPException(status_code=404, detail="转写记录不存在")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_speech_transcripts(
    payload: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> BatchDeleteResponse:
    result = await db.execute(
        text("DELETE FROM speech_transcripts WHERE transcript_id = ANY(:ids) RETURNING transcript_id"),
        {"ids": payload.ids},
    )
    await db.commit()
    deleted = len(result.fetchall())
    return BatchDeleteResponse(deleted=deleted)
