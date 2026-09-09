from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta
from .recording_document_metadata import PREFIX, public_reason
from .transcript_final_scope import SCOPE_MARKER, excluded_ids_from_reasons


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
    source_transcript_ids: list[str] = Field(default_factory=list)
    is_merged: bool = False
    final_excluded: bool = False


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
    transcript_id: str | None = None
    corrected_text: str
    correction_reason: str | None = None
    corrected_by: str | None = None
    created_at: datetime
    updated_at: datetime


class SaveMergedTranscriptCorrectionIn(ApiModel):
    transcript_ids: list[str] = Field(min_length=2)
    corrected_text: str
    correction_reason: str | None = None
    corrected_by: str | None = None

    @field_validator("transcript_ids")
    @classmethod
    def validate_transcript_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) < 2:
            raise ValueError("合并修订至少需要两条实时转写")
        if len(set(normalized)) != len(normalized):
            raise ValueError("不能重复选择同一条实时转写")
        return normalized

    @field_validator("corrected_text")
    @classmethod
    def validate_merged_corrected_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("corrected_text 不能为空")
        return normalized


class UpdateMergedTranscriptCorrectionIn(ApiModel):
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


class MergedTranscriptCorrectionOut(ApiModel):
    id: str
    transcript_ids: list[str]
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
                       COUNT(tcm.correction_id)::int AS corrected_count
                FROM groups g
                JOIN chat_sessions cs ON cs.group_id = g.id
                JOIN speech_transcripts t ON t.session_id = cs.id
                LEFT JOIN speech_transcript_correction_members tcm
                       ON tcm.transcript_id = t.transcript_id
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
                       COUNT(tcm.correction_id)::int AS corrected_count,
                       cs.created_at,
                       cs.started_at
                FROM chat_sessions cs
                JOIN groups g ON g.id = cs.group_id
                JOIN speech_transcripts t ON t.session_id = cs.id
                LEFT JOIN speech_transcript_correction_members tcm
                       ON tcm.transcript_id = t.transcript_id
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
    content_view: str = "latest",
    db: AsyncSession = Depends(get_db),
) -> Page[CorrectableTranscriptOut]:
    if content_view not in ('original', 'latest'):
        raise HTTPException(400, 'content_view 只能是 original 或 latest')
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
        where.append("COALESCE(t.original_text, t.text, '') ILIKE :keyword" if content_view == 'original' else "COALESCE(tc.corrected_text, t.text, '') ILIKE :keyword")
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
        LEFT JOIN speech_transcript_correction_members tcm
               ON tcm.transcript_id = t.transcript_id
        LEFT JOIN speech_transcript_corrections tc
               ON tc.id = tcm.correction_id
        LEFT JOIN LATERAL (
            SELECT ARRAY_AGG(member.transcript_id ORDER BY member.order_index) AS transcript_ids,
                   COUNT(*)::int AS member_count
            FROM speech_transcript_correction_members member
            WHERE member.correction_id = tc.id
        ) correction_members ON TRUE
    """
    count_joins = joins.split("        LEFT JOIN LATERAL", 1)[0]
    total = (
        await db.execute(
            text(f"SELECT COUNT(*) {count_joins} WHERE {where_sql}"),
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
                       COALESCE(t.original_text, t.text) AS original_text,
                       COALESCE(tc.corrected_text, t.text) AS effective_text,
                       t.start,
                       t."end",
                       t.created_at,
                       (tc.id IS NOT NULL) AS is_corrected,
                       tc.id AS correction_id,
                       split_part(tc.correction_reason, E'\\n[recording-document-v1]', 1) AS correction_reason,
                       tc.corrected_by,
                       tc.updated_at AS corrected_at,
                       COALESCE(
                           correction_members.transcript_ids,
                           ARRAY[t.transcript_id]::text[]
                       ) AS source_transcript_ids,
                       (COALESCE(correction_members.member_count, 0) > 1) AS is_merged
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
    # Read scope from the entire session, not just the filtered/current page.
    # Metadata lives with saved AI corrections, so refresh/Redis expiry cannot
    # bring discarded ASR noise back into the final version.
    scope_rows = (await db.execute(text("""
        SELECT DISTINCT tc.correction_reason
        FROM speech_transcript_corrections tc
        JOIN speech_transcript_correction_members member ON member.correction_id = tc.id
        JOIN speech_transcripts source ON source.transcript_id = member.transcript_id
        WHERE source.session_id = :session_id
          AND tc.correction_reason LIKE 'AI 整场匹配%'
    """), {"session_id": session_id})).mappings().all()
    excluded = excluded_ids_from_reasons(row["correction_reason"] for row in scope_rows)
    items = []
    for row in rows:
        item = dict(row)
        item["final_excluded"] = item["transcript_id"] in excluded and not item["is_corrected"]
        if item.get("correction_reason"):
            item["correction_reason"] = public_reason(item["correction_reason"].split(SCOPE_MARKER, 1)[0])
        items.append(CorrectableTranscriptOut.model_validate(item))
    return Page[CorrectableTranscriptOut](
        items=items,
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
    protected = (await db.execute(text("""
        SELECT 1 FROM speech_transcript_corrections c
        JOIN speech_transcript_correction_members m ON m.correction_id = c.id
        WHERE m.transcript_id = :id AND c.correction_reason LIKE :prefix
    """), {'id': transcript_id, 'prefix': PREFIX + '%'})).first()
    if protected:
        raise HTTPException(409, '此条属于完整录音修订，请在最终版本面板重新预览和保存')
    existing_membership = (
        await db.execute(
            text(
                """
                SELECT member.correction_id, COUNT(all_members.transcript_id)::int AS member_count
                FROM speech_transcript_correction_members member
                JOIN speech_transcript_correction_members all_members
                  ON all_members.correction_id = member.correction_id
                WHERE member.transcript_id = :transcript_id
                GROUP BY member.correction_id
                """
            ),
            {"transcript_id": transcript_id},
        )
    ).mappings().first()
    if existing_membership and existing_membership["member_count"] > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该实时转写属于合并修订，请直接编辑或先撤销合并修订",
        )

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
    await db.execute(
        text(
            """
            INSERT INTO speech_transcript_correction_members (
                correction_id, transcript_id, order_index
            ) VALUES (
                :correction_id, :transcript_id, 0
            )
            ON CONFLICT (transcript_id)
            DO UPDATE SET
                correction_id = EXCLUDED.correction_id,
                order_index = 0
            """
        ),
        {"correction_id": row["id"], "transcript_id": transcript_id},
    )
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
    membership = (
        await db.execute(
            text(
                """
                SELECT member.correction_id, COUNT(all_members.transcript_id)::int AS member_count
                FROM speech_transcript_correction_members member
                JOIN speech_transcript_correction_members all_members
                  ON all_members.correction_id = member.correction_id
                WHERE member.transcript_id = :transcript_id
                GROUP BY member.correction_id
                """
            ),
            {"transcript_id": transcript_id},
        )
    ).mappings().first()
    if membership and membership["member_count"] > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该实时转写属于合并修订，请撤销整个合并修订",
        )

    result = await db.execute(
        text(
            """
            DELETE FROM speech_transcript_corrections
            WHERE id = COALESCE(
                :correction_id,
                (SELECT id FROM speech_transcript_corrections WHERE transcript_id = :transcript_id)
            )
            RETURNING id
            """
        ),
        {
            "transcript_id": transcript_id,
            "correction_id": membership["correction_id"] if membership else None,
        },
    )
    if not result.first():
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该转写没有人工修订")
    await db.commit()


@router.post(
    "/sessions/{session_id}/merged",
    response_model=MergedTranscriptCorrectionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_merged_transcript_correction(
    session_id: str,
    payload: SaveMergedTranscriptCorrectionIn,
    db: AsyncSession = Depends(get_db),
) -> MergedTranscriptCorrectionOut:
    rows = (
        await db.execute(
            text(
                """
                SELECT t.transcript_id
                FROM speech_transcripts t
                JOIN chat_sessions cs ON cs.id = t.session_id
                JOIN groups g ON g.id = cs.group_id
                WHERE t.session_id = :session_id
                  AND t.transcript_id = ANY(:transcript_ids)
                  AND g.condition IN ('glasses', 'app_notification')
                ORDER BY t.start ASC NULLS LAST,
                         t.created_at ASC,
                         t.transcript_id ASC
                """
            ),
            {"session_id": session_id, "transcript_ids": payload.transcript_ids},
        )
    ).mappings().all()
    ordered_ids = [row["transcript_id"] for row in rows]
    if len(ordered_ids) != len(payload.transcript_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所选实时转写不在同一个辅助条件会话中，请刷新后重试",
        )

    occupied = (
        await db.execute(
            text(
                """
                SELECT transcript_id
                FROM speech_transcript_correction_members
                WHERE transcript_id = ANY(:transcript_ids)
                LIMIT 1
                """
            ),
            {"transcript_ids": ordered_ids},
        )
    ).first()
    if occupied:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所选内容中已有人工修订，请先撤销原修订再合并",
        )

    correction_id = "stc" + uuid.uuid4().hex[:12]
    try:
        correction_row = (
            await db.execute(
                text(
                    """
                    INSERT INTO speech_transcript_corrections (
                        id, transcript_id, corrected_text, correction_reason,
                        corrected_by, created_at, updated_at
                    ) VALUES (
                        :id, NULL, :corrected_text, :correction_reason,
                        :corrected_by, NOW(), NOW()
                    )
                    RETURNING id, corrected_text, correction_reason,
                              corrected_by, created_at, updated_at
                    """
                ),
                {
                    "id": correction_id,
                    "corrected_text": payload.corrected_text,
                    "correction_reason": (payload.correction_reason or "").strip() or None,
                    "corrected_by": (payload.corrected_by or "").strip() or None,
                },
            )
        ).mappings().one()
        for order_index, transcript_id in enumerate(ordered_ids):
            await db.execute(
                text(
                    """
                    INSERT INTO speech_transcript_correction_members (
                        correction_id, transcript_id, order_index
                    ) VALUES (
                        :correction_id, :transcript_id, :order_index
                    )
                    """
                ),
                {
                    "correction_id": correction_id,
                    "transcript_id": transcript_id,
                    "order_index": order_index,
                },
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所选内容已被其他修订占用，请刷新后重试",
        ) from exc

    return MergedTranscriptCorrectionOut.model_validate(
        {**dict(correction_row), "transcript_ids": ordered_ids}
    )


async def _get_merged_correction(
    db: AsyncSession,
    correction_id: str,
) -> tuple[dict[str, Any], list[str]]:
    row = (
        await db.execute(
            text(
                """
                SELECT tc.id, tc.corrected_text, tc.correction_reason,
                       tc.corrected_by, tc.created_at, tc.updated_at,
                       ARRAY_AGG(member.transcript_id ORDER BY member.order_index) AS transcript_ids,
                       COUNT(member.transcript_id)::int AS member_count
                FROM speech_transcript_corrections tc
                JOIN speech_transcript_correction_members member
                  ON member.correction_id = tc.id
                WHERE tc.id = :correction_id
                GROUP BY tc.id, tc.corrected_text, tc.correction_reason,
                         tc.corrected_by, tc.created_at, tc.updated_at
                """
            ),
            {"correction_id": correction_id},
        )
    ).mappings().first()
    if not row or row["member_count"] < 2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合并修订不存在",
        )
    data = dict(row)
    transcript_ids = list(data.pop("transcript_ids"))
    data.pop("member_count")
    return data, transcript_ids


@router.put(
    "/merged/{correction_id}",
    response_model=MergedTranscriptCorrectionOut,
)
async def update_merged_transcript_correction(
    correction_id: str,
    payload: UpdateMergedTranscriptCorrectionIn,
    db: AsyncSession = Depends(get_db),
) -> MergedTranscriptCorrectionOut:
    existing, transcript_ids = await _get_merged_correction(db, correction_id)
    if (existing.get('correction_reason') or '').startswith(PREFIX):
        raise HTTPException(409, '此份为完整录音修订，请在最终版本面板重新预览和保存')
    row = (
        await db.execute(
            text(
                """
                UPDATE speech_transcript_corrections
                SET corrected_text = :corrected_text,
                    correction_reason = :correction_reason,
                    corrected_by = :corrected_by,
                    updated_at = NOW()
                WHERE id = :correction_id
                RETURNING id, corrected_text, correction_reason,
                          corrected_by, created_at, updated_at
                """
            ),
            {
                "correction_id": correction_id,
                "corrected_text": payload.corrected_text,
                "correction_reason": (payload.correction_reason or "").strip() or None,
                "corrected_by": (payload.corrected_by or "").strip() or None,
            },
        )
    ).mappings().one()
    await db.commit()
    return MergedTranscriptCorrectionOut.model_validate(
        {**dict(row), "transcript_ids": transcript_ids}
    )


@router.delete(
    "/merged/{correction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_merged_transcript_correction(
    correction_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_merged_correction(db, correction_id)
    await db.execute(
        text("DELETE FROM speech_transcript_corrections WHERE id = :correction_id"),
        {"correction_id": correction_id},
    )
    await db.commit()
