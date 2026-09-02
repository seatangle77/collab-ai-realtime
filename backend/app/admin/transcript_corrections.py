from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(
    prefix="/api/admin/transcript-corrections",
    tags=["admin-transcript-corrections"],
    dependencies=[Depends(require_admin)],
)

ASSISTED_CONDITIONS = {"glasses", "app_notification"}
CORRECTION_STATUSES = {"corrected", "uncorrected"}


class TranscriptCorrectionGroupOut(ApiModel):
    group_id: str
    group_name: str
    condition: str
    transcript_count: int
    corrected_count: int


class TranscriptCorrectionSessionOut(ApiModel):
    session_id: str
    session_title: str | None = None
    group_id: str
    group_name: str
    condition: str
    transcript_count: int
    corrected_count: int
    created_at: datetime
    started_at: datetime | None = None


class CorrectableTranscriptOut(ApiModel):
    transcript_id: str
    group_id: str
    session_id: str
    speaker_user_id: str | None = None
    speaker_name: str
    original_text: str | None = None
    effective_text: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    created_at: datetime | None = None
    is_corrected: bool
    correction_id: str | None = None
    correction_reason: str | None = None
    corrected_by: str | None = None
    corrected_at: datetime | None = None


class SaveTranscriptCorrectionIn(ApiModel):
    corrected_text: str
    correction_reason: str | None = None
    corrected_by: str | None = None

    @field_validator("corrected_text")
    @classmethod
    def validate_corrected_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("corrected_text 不能为空")
        return normalized


class TranscriptCorrectionOut(ApiModel):
    id: str
    transcript_id: str
    corrected_text: str
    correction_reason: str | None = None
    corrected_by: str | None = None
    created_at: datetime
    updated_at: datetime


def _validate_condition(condition: str | None) -> None:
    if condition is not None and condition not in ASSISTED_CONDITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="condition 只能是 glasses 或 app_notification",
        )


async def _get_assisted_transcript(
    db: AsyncSession,
    transcript_id: str,
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT t.transcript_id, t.session_id, t.group_id
            FROM speech_transcripts t
            JOIN chat_sessions cs ON cs.id = t.session_id
            JOIN groups g ON g.id = cs.group_id
            WHERE t.transcript_id = :transcript_id
              AND g.condition IN ('glasses', 'app_notification')
            """
        ),
        {"transcript_id": transcript_id},
    )
    row = result.mappings().first()
    if row:
        return dict(row)

    exists = await db.execute(
        text("SELECT 1 FROM speech_transcripts WHERE transcript_id = :transcript_id"),
        {"transcript_id": transcript_id},
    )
    if not exists.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="原始转写不存在")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="该转写不属于辅助条件小组，不能在此页面修订",
    )


@router.get("/groups", response_model=list[TranscriptCorrectionGroupOut])
async def list_transcript_correction_groups(
    condition: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[TranscriptCorrectionGroupOut]:
    _validate_condition(condition)
    condition_filter = "AND g.condition = :condition" if condition else ""
    params = {"condition": condition} if condition else {}
    rows = (
        await db.execute(
            text(
                f"""
                SELECT g.id AS group_id,
                       g.name AS group_name,
                       g.condition,
                       COUNT(t.transcript_id)::int AS transcript_count,
                       COUNT(tc.id)::int AS corrected_count
                FROM groups g
                JOIN chat_sessions cs ON cs.group_id = g.id
                JOIN speech_transcripts t ON t.session_id = cs.id
                LEFT JOIN speech_transcript_corrections tc
                       ON tc.transcript_id = t.transcript_id
                WHERE g.condition IN ('glasses', 'app_notification')
                  {condition_filter}
                GROUP BY g.id, g.name, g.condition
                ORDER BY g.name ASC, g.id ASC
                """
            ),
            params,
        )
    ).mappings().all()
    return [TranscriptCorrectionGroupOut.model_validate(dict(row)) for row in rows]


@router.get("/sessions", response_model=list[TranscriptCorrectionSessionOut])
async def list_transcript_correction_sessions(
    group_id: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> list[TranscriptCorrectionSessionOut]:
    rows = (
        await db.execute(
            text(
                """
                SELECT cs.id AS session_id,
                       cs.session_title,
                       cs.group_id,
                       g.name AS group_name,
                       g.condition,
                       COUNT(t.transcript_id)::int AS transcript_count,
                       COUNT(tc.id)::int AS corrected_count,
                       cs.created_at,
                       cs.started_at
                FROM chat_sessions cs
                JOIN groups g ON g.id = cs.group_id
                JOIN speech_transcripts t ON t.session_id = cs.id
                LEFT JOIN speech_transcript_corrections tc
                       ON tc.transcript_id = t.transcript_id
                WHERE cs.group_id = :group_id
                  AND g.condition IN ('glasses', 'app_notification')
                GROUP BY cs.id, cs.session_title, cs.group_id,
                         g.name, g.condition, cs.created_at, cs.started_at
                ORDER BY cs.created_at ASC, cs.id ASC
                """
            ),
            {"group_id": group_id},
        )
    ).mappings().all()
    return [TranscriptCorrectionSessionOut.model_validate(dict(row)) for row in rows]


@router.get(
    "/sessions/{session_id}/transcripts",
    response_model=Page[CorrectableTranscriptOut],
)
async def list_correctable_transcripts(
    session_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    correction_status: str | None = None,
    speaker: str | None = None,
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[CorrectableTranscriptOut]:
    if correction_status is not None and correction_status not in CORRECTION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="correction_status 只能是 corrected 或 uncorrected",
        )

    session_result = await db.execute(
        text(
            """
            SELECT 1
            FROM chat_sessions cs
            JOIN groups g ON g.id = cs.group_id
            WHERE cs.id = :session_id
              AND g.condition IN ('glasses', 'app_notification')
            """
        ),
        {"session_id": session_id},
    )
    if not session_result.first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="辅助条件会话不存在",
        )

    where = ["t.session_id = :session_id"]
    params: dict[str, Any] = {"session_id": session_id}
    if correction_status == "corrected":
        where.append("tc.id IS NOT NULL")
    elif correction_status == "uncorrected":
        where.append("tc.id IS NULL")
    if speaker and speaker.strip():
        where.append("COALESCE(u.name, t.speaker, '') ILIKE :speaker")
        params["speaker"] = f"%{speaker.strip()}%"
    if keyword and keyword.strip():
        where.append("COALESCE(tc.corrected_text, t.text, '') ILIKE :keyword")
        params["keyword"] = f"%{keyword.strip()}%"
    where_sql = " AND ".join(where)

    joins = """
        FROM speech_transcripts t
        LEFT JOIN users_info u
               ON u.id = COALESCE(
                   t.speaker_user_id,
                   t.user_id,
                   NULLIF(BTRIM(t.speaker), '')
               )
        LEFT JOIN speech_transcript_corrections tc
               ON tc.transcript_id = t.transcript_id
    """
    total = (
        await db.execute(
            text(f"SELECT COUNT(*) {joins} WHERE {where_sql}"),
            params,
        )
    ).scalar_one()
    rows = (
        await db.execute(
            text(
                f"""
                SELECT t.transcript_id,
                       t.group_id,
                       t.session_id,
                       COALESCE(t.speaker_user_id, t.user_id, u.id) AS speaker_user_id,
                       COALESCE(u.name, t.speaker, '未知说话人') AS speaker_name,
                       t.text AS original_text,
                       COALESCE(tc.corrected_text, t.text) AS effective_text,
                       t.start,
                       t."end",
                       t.created_at,
                       (tc.id IS NOT NULL) AS is_corrected,
                       tc.id AS correction_id,
                       tc.correction_reason,
                       tc.corrected_by,
                       tc.updated_at AS corrected_at
                {joins}
                WHERE {where_sql}
                ORDER BY t.start ASC NULLS LAST,
                         t.created_at ASC,
                         t.transcript_id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                **params,
                "limit": page_size,
                "offset": (page - 1) * page_size,
            },
        )
    ).mappings().all()
    return Page[CorrectableTranscriptOut](
        items=[CorrectableTranscriptOut.model_validate(dict(row)) for row in rows],
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.put(
    "/transcripts/{transcript_id}",
    response_model=TranscriptCorrectionOut,
)
async def save_transcript_correction(
    transcript_id: str,
    payload: SaveTranscriptCorrectionIn,
    db: AsyncSession = Depends(get_db),
) -> TranscriptCorrectionOut:
    await _get_assisted_transcript(db, transcript_id)
    correction_id = "stc" + uuid.uuid4().hex[:12]
    result = await db.execute(
        text(
            """
            INSERT INTO speech_transcript_corrections (
                id, transcript_id, corrected_text, correction_reason,
                corrected_by, created_at, updated_at
            ) VALUES (
                :id, :transcript_id, :corrected_text, :correction_reason,
                :corrected_by, NOW(), NOW()
            )
            ON CONFLICT (transcript_id)
            DO UPDATE SET
                corrected_text = EXCLUDED.corrected_text,
                correction_reason = EXCLUDED.correction_reason,
                corrected_by = EXCLUDED.corrected_by,
                updated_at = NOW()
            RETURNING id, transcript_id, corrected_text, correction_reason,
                      corrected_by, created_at, updated_at
            """
        ),
        {
            "id": correction_id,
            "transcript_id": transcript_id,
            "corrected_text": payload.corrected_text,
            "correction_reason": (payload.correction_reason or "").strip() or None,
            "corrected_by": (payload.corrected_by or "").strip() or None,
        },
    )
    row = result.mappings().one()
    await db.commit()
    return TranscriptCorrectionOut.model_validate(dict(row))


@router.delete(
    "/transcripts/{transcript_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transcript_correction(
    transcript_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        text(
            """
            DELETE FROM speech_transcript_corrections
            WHERE transcript_id = :transcript_id
            RETURNING id
            """
        ),
        {"transcript_id": transcript_id},
    )
    if not result.first():
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该转写没有人工修订")
    await db.commit()
