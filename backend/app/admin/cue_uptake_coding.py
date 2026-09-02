from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..db import get_db
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(
    prefix="/api/admin/cue-uptake-coding",
    tags=["admin-cue-uptake-coding"],
    dependencies=[Depends(require_admin)],
)

VALID_CONDITIONS = {"glasses", "app_notification"}
VALID_CODING_STATUSES = {"coded", "uncoded"}
VALID_UPTAKE_CODES = {
    "not_discussed",
    "discussed_not_adopted",
    "discussed_adopted",
    "uncertain",
    "not_included",
}
ELIGIBLE_EVENT_WHERE = """
    pl.delivery_status = 'delivered'
    AND pl.target_user_id IS NOT NULL
    AND NULLIF(BTRIM(pl.push_content), '') IS NOT NULL
    AND g.condition IN ('glasses', 'app_notification')
    AND COALESCE(pq.state_type, ds.state_type) IN ('stagnation', 'shallow')
"""


class CueCodingOut(ApiModel):
    id: str
    push_log_id: str
    coder_role: str
    uptake_code: str
    evidence_transcript_ids: list[str]
    coding_reason: str | None = None
    coded_by: str | None = None
    coded_at: datetime
    created_at: datetime
    updated_at: datetime


class CueEventOut(ApiModel):
    push_log_id: str
    queue_id: str | None = None
    session_id: str
    session_title: str | None = None
    group_id: str
    group_name: str
    condition: str
    target_user_id: str
    target_user_name: str
    push_content: str
    state_type: str
    received_at: datetime
    delivery_reason: str | None = None
    possible_duplicate: bool = False
    coding: CueCodingOut | None = None


class CueContextMemberOut(ApiModel):
    user_id: str
    user_name: str
    role: str | None = None


class CueContextTranscriptOut(ApiModel):
    transcript_id: str
    speaker_user_id: str | None = None
    speaker_name: str
    text: str | None = None
    original_text: str | None = None
    is_corrected: bool = False
    correction_reason: str | None = None
    corrected_by: str | None = None
    corrected_at: datetime | None = None
    start: datetime | None = None
    end: datetime | None = None
    created_at: datetime | None = None


class CueSessionContextOut(ApiModel):
    session_id: str
    session_title: str | None = None
    group_id: str
    group_name: str
    condition: str
    members: list[CueContextMemberOut]
    transcripts: list[CueContextTranscriptOut]
    cues: list[CueEventOut]


class SaveCueCodingIn(ApiModel):
    coder_role: str = "primary"
    uptake_code: str
    evidence_transcript_ids: list[str] = Field(default_factory=list)
    coding_reason: str | None = None
    coded_by: str | None = None

    @field_validator("coder_role")
    @classmethod
    def validate_coder_role(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("coder_role 不能为空")
        if len(normalized) > 20:
            raise ValueError("coder_role 最多 20 个字符")
        return normalized

    @field_validator("uptake_code")
    @classmethod
    def validate_uptake_code(cls, value: str) -> str:
        if value not in VALID_UPTAKE_CODES:
            raise ValueError(f"uptake_code 必须是：{', '.join(sorted(VALID_UPTAKE_CODES))}")
        return value

    @field_validator("evidence_transcript_ids")
    @classmethod
    def deduplicate_evidence_ids(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in value:
            transcript_id = raw.strip()
            if transcript_id and transcript_id not in seen:
                seen.add(transcript_id)
                result.append(transcript_id)
        return result


class CueProgressOut(ApiModel):
    total: int
    coded: int
    uncoded: int
    completion_rate: float
    by_code: dict[str, int]


class CueCodingGroupOut(ApiModel):
    group_id: str
    group_name: str
    condition: str
    event_count: int


def _validate_optional_filters(
    *,
    condition: str | None = None,
    coding_status: str | None = None,
    uptake_code: str | None = None,
) -> None:
    if condition is not None and condition not in VALID_CONDITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"condition 必须是：{', '.join(sorted(VALID_CONDITIONS))}",
        )
    if coding_status is not None and coding_status not in VALID_CODING_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"coding_status 必须是：{', '.join(sorted(VALID_CODING_STATUSES))}",
        )
    if uptake_code is not None and uptake_code not in VALID_UPTAKE_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"uptake_code 必须是：{', '.join(sorted(VALID_UPTAKE_CODES))}",
        )


def _normalize_coder_role(coder_role: str) -> str:
    normalized = coder_role.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="coder_role 不能为空",
        )
    return normalized


def _build_event_filters(
    *,
    coder_role: str,
    condition: str | None = None,
    group_id: str | None = None,
    session_id: str | None = None,
    target_user_id: str | None = None,
    coding_status: str | None = None,
    uptake_code: str | None = None,
    keyword: str | None = None,
) -> tuple[str, dict[str, Any]]:
    where = [ELIGIBLE_EVENT_WHERE]
    params: dict[str, Any] = {"coder_role": coder_role}

    if condition:
        where.append("g.condition = :condition")
        params["condition"] = condition
    if group_id:
        where.append("g.id = :group_id")
        params["group_id"] = group_id
    if session_id:
        where.append("pl.session_id = :session_id")
        params["session_id"] = session_id
    if target_user_id:
        where.append("pl.target_user_id = :target_user_id")
        params["target_user_id"] = target_user_id
    if coding_status == "coded":
        where.append("cuc.id IS NOT NULL")
    elif coding_status == "uncoded":
        where.append("cuc.id IS NULL")
    if uptake_code:
        where.append("cuc.uptake_code = :uptake_code")
        params["uptake_code"] = uptake_code
    if keyword and keyword.strip():
        where.append("pl.push_content ILIKE :keyword")
        params["keyword"] = f"%{keyword.strip()}%"

    return " AND ".join(f"({item.strip()})" for item in where), params


def _event_select(where_sql: str) -> str:
    return f"""
        SELECT
            pl.id AS push_log_id,
            pl.queue_id,
            pl.session_id,
            cs.session_title,
            cs.group_id,
            g.name AS group_name,
            g.condition,
            pl.target_user_id,
            COALESCE(target_user.name, pl.target_user_id) AS target_user_name,
            pl.push_content,
            COALESCE(pq.state_type, ds.state_type) AS state_type,
            COALESCE(pl.delivered_at, pl.triggered_at) AS received_at,
            pl.delivery_reason,
            EXISTS (
                SELECT 1
                FROM push_logs duplicate
                WHERE duplicate.id <> pl.id
                  AND duplicate.delivery_status = 'delivered'
                  AND duplicate.session_id = pl.session_id
                  AND duplicate.target_user_id = pl.target_user_id
                  AND (
                      (pl.queue_id IS NOT NULL AND duplicate.queue_id = pl.queue_id)
                      OR (
                          pl.queue_id IS NULL
                          AND duplicate.queue_id IS NULL
                          AND BTRIM(COALESCE(duplicate.push_content, '')) = BTRIM(pl.push_content)
                          AND ABS(EXTRACT(EPOCH FROM (duplicate.triggered_at - pl.triggered_at))) <= 10
                      )
                  )
            ) AS possible_duplicate,
            cuc.id AS coding_id,
            cuc.coder_role AS coding_coder_role,
            cuc.uptake_code AS coding_uptake_code,
            cuc.evidence_transcript_ids AS coding_evidence_transcript_ids,
            cuc.coding_reason AS coding_reason,
            cuc.coded_by AS coding_coded_by,
            cuc.coded_at AS coding_coded_at,
            cuc.created_at AS coding_created_at,
            cuc.updated_at AS coding_updated_at
        FROM push_logs pl
        JOIN chat_sessions cs ON cs.id = pl.session_id
        JOIN groups g ON g.id = cs.group_id
        JOIN users_info target_user ON target_user.id = pl.target_user_id
        LEFT JOIN push_queue pq ON pq.id = pl.queue_id
        LEFT JOIN discussion_states ds ON ds.id = pl.state_id
        LEFT JOIN cue_uptake_codes cuc
               ON cuc.push_log_id = pl.id
              AND cuc.coder_role = :coder_role
        WHERE {where_sql}
    """


def _row_to_coding(row: dict[str, Any]) -> CueCodingOut | None:
    if not row.get("coding_id"):
        return None
    return CueCodingOut(
        id=row["coding_id"],
        push_log_id=row["push_log_id"],
        coder_role=row["coding_coder_role"],
        uptake_code=row["coding_uptake_code"],
        evidence_transcript_ids=list(row.get("coding_evidence_transcript_ids") or []),
        coding_reason=row.get("coding_reason"),
        coded_by=row.get("coding_coded_by"),
        coded_at=row["coding_coded_at"],
        created_at=row["coding_created_at"],
        updated_at=row["coding_updated_at"],
    )


def _row_to_event(row: dict[str, Any]) -> CueEventOut:
    return CueEventOut(
        push_log_id=row["push_log_id"],
        queue_id=row.get("queue_id"),
        session_id=row["session_id"],
        session_title=row.get("session_title"),
        group_id=row["group_id"],
        group_name=row["group_name"],
        condition=row["condition"],
        target_user_id=row["target_user_id"],
        target_user_name=row["target_user_name"],
        push_content=row["push_content"],
        state_type=row["state_type"],
        received_at=row["received_at"],
        delivery_reason=row.get("delivery_reason"),
        possible_duplicate=bool(row.get("possible_duplicate")),
        coding=_row_to_coding(row),
    )


async def _get_eligible_event_session(
    db: AsyncSession,
    push_log_id: str,
) -> str:
    result = await db.execute(
        text(
            f"""
            SELECT pl.session_id
            FROM push_logs pl
            JOIN chat_sessions cs ON cs.id = pl.session_id
            JOIN groups g ON g.id = cs.group_id
            LEFT JOIN push_queue pq ON pq.id = pl.queue_id
            LEFT JOIN discussion_states ds ON ds.id = pl.state_id
            WHERE pl.id = :push_log_id
              AND {ELIGIBLE_EVENT_WHERE}
            """
        ),
        {"push_log_id": push_log_id},
    )
    row = result.mappings().first()
    if row:
        return row["session_id"]

    exists = await db.execute(
        text("SELECT 1 FROM push_logs WHERE id = :push_log_id"),
        {"push_log_id": push_log_id},
    )
    if not exists.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推送日志不存在")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="该推送不符合提示采纳编码的纳入条件",
    )


@router.get("/groups", response_model=list[CueCodingGroupOut])
async def list_cue_coding_groups(
    condition: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[CueCodingGroupOut]:
    _validate_optional_filters(condition=condition)
    condition_filter = "AND g.condition = :condition" if condition else ""
    params = {"condition": condition} if condition else {}
    rows = (
        await db.execute(
            text(
                f"""
                SELECT g.id AS group_id,
                       g.name AS group_name,
                       g.condition,
                       COUNT(*)::int AS event_count
                FROM push_logs pl
                JOIN chat_sessions cs ON cs.id = pl.session_id
                JOIN groups g ON g.id = cs.group_id
                LEFT JOIN push_queue pq ON pq.id = pl.queue_id
                LEFT JOIN discussion_states ds ON ds.id = pl.state_id
                WHERE {ELIGIBLE_EVENT_WHERE}
                  {condition_filter}
                GROUP BY g.id, g.name, g.condition
                ORDER BY g.name ASC, g.id ASC
                """
            ),
            params,
        )
    ).mappings().all()
    return [CueCodingGroupOut.model_validate(dict(row)) for row in rows]


@router.get("/events", response_model=Page[CueEventOut])
async def list_cue_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    condition: str | None = None,
    group_id: str | None = None,
    session_id: str | None = None,
    target_user_id: str | None = None,
    coding_status: str | None = None,
    uptake_code: str | None = None,
    coder_role: str = Query("primary", min_length=1, max_length=20),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[CueEventOut]:
    _validate_optional_filters(
        condition=condition,
        coding_status=coding_status,
        uptake_code=uptake_code,
    )
    coder_role = _normalize_coder_role(coder_role)
    where_sql, params = _build_event_filters(
        coder_role=coder_role,
        condition=condition,
        group_id=group_id,
        session_id=session_id,
        target_user_id=target_user_id,
        coding_status=coding_status,
        uptake_code=uptake_code,
        keyword=keyword,
    )
    total = (
        await db.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM push_logs pl
                JOIN chat_sessions cs ON cs.id = pl.session_id
                JOIN groups g ON g.id = cs.group_id
                LEFT JOIN push_queue pq ON pq.id = pl.queue_id
                LEFT JOIN discussion_states ds ON ds.id = pl.state_id
                LEFT JOIN cue_uptake_codes cuc
                       ON cuc.push_log_id = pl.id
                      AND cuc.coder_role = :coder_role
                WHERE {where_sql}
                """
            ),
            params,
        )
    ).scalar_one()

    rows = (
        await db.execute(
            text(
                _event_select(where_sql)
                + """
                ORDER BY g.name ASC, cs.created_at ASC,
                         COALESCE(pl.delivered_at, pl.triggered_at) ASC, pl.id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        )
    ).mappings().all()

    return Page[CueEventOut](
        items=[_row_to_event(dict(row)) for row in rows],
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


@router.get(
    "/sessions/{session_id}/context",
    response_model=CueSessionContextOut,
)
async def get_cue_session_context(
    session_id: str,
    coder_role: str = Query("primary", min_length=1, max_length=20),
    db: AsyncSession = Depends(get_db),
) -> CueSessionContextOut:
    coder_role = _normalize_coder_role(coder_role)
    session_result = await db.execute(
        text(
            """
            SELECT cs.id AS session_id, cs.session_title, cs.group_id,
                   g.name AS group_name, g.condition
            FROM chat_sessions cs
            JOIN groups g ON g.id = cs.group_id
            WHERE cs.id = :session_id
            """
        ),
        {"session_id": session_id},
    )
    session_row = session_result.mappings().first()
    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    member_rows = (
        await db.execute(
            text(
                """
                SELECT gm.user_id, u.name AS user_name, gm.role
                FROM group_memberships gm
                JOIN users_info u ON u.id = gm.user_id
                WHERE gm.group_id = :group_id AND gm.status = 'active'
                ORDER BY u.name ASC, gm.user_id ASC
                """
            ),
            {"group_id": session_row["group_id"]},
        )
    ).mappings().all()

    transcript_rows = (
        await db.execute(
            text(
                """
                SELECT t.transcript_id,
                       COALESCE(t.speaker_user_id, t.user_id, u.id) AS speaker_user_id,
                       COALESCE(u.name, t.speaker, '未知说话人') AS speaker_name,
                       COALESCE(tc.corrected_text, t.text) AS text,
                       t.text AS original_text,
                       (tc.id IS NOT NULL) AS is_corrected,
                       tc.correction_reason,
                       tc.corrected_by,
                       tc.updated_at AS corrected_at,
                       t.start, t."end", t.created_at
                FROM speech_transcripts t
                LEFT JOIN users_info u
                       ON u.id = COALESCE(
                           t.speaker_user_id,
                           t.user_id,
                           NULLIF(BTRIM(t.speaker), '')
                       )
                LEFT JOIN speech_transcript_corrections tc
                       ON tc.transcript_id = t.transcript_id
                WHERE t.session_id = :session_id
                ORDER BY t.start ASC NULLS LAST, t.created_at ASC, t.transcript_id ASC
                """
            ),
            {"session_id": session_id},
        )
    ).mappings().all()

    where_sql, params = _build_event_filters(
        coder_role=coder_role,
        session_id=session_id,
    )
    cue_rows = (
        await db.execute(
            text(
                _event_select(where_sql)
                + """
                ORDER BY COALESCE(pl.delivered_at, pl.triggered_at) ASC, pl.id ASC
                """
            ),
            params,
        )
    ).mappings().all()

    return CueSessionContextOut(
        session_id=session_row["session_id"],
        session_title=session_row.get("session_title"),
        group_id=session_row["group_id"],
        group_name=session_row["group_name"],
        condition=session_row["condition"],
        members=[CueContextMemberOut.model_validate(dict(row)) for row in member_rows],
        transcripts=[CueContextTranscriptOut.model_validate(dict(row)) for row in transcript_rows],
        cues=[_row_to_event(dict(row)) for row in cue_rows],
    )


@router.put("/events/{push_log_id}/coding", response_model=CueCodingOut)
async def save_cue_coding(
    push_log_id: str,
    payload: SaveCueCodingIn,
    db: AsyncSession = Depends(get_db),
) -> CueCodingOut:
    session_id = await _get_eligible_event_session(db, push_log_id)

    if payload.uptake_code in {"discussed_not_adopted", "discussed_adopted"}:
        if not payload.evidence_transcript_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="讨论相关编码至少需要选择一条证据发言",
            )
    if payload.uptake_code == "uncertain" and not (payload.coding_reason or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法判断时必须填写判断原因",
        )

    if payload.evidence_transcript_ids:
        evidence_rows = (
            await db.execute(
                text(
                    """
                    SELECT transcript_id
                    FROM speech_transcripts
                    WHERE transcript_id = ANY(:transcript_ids)
                      AND session_id = :session_id
                    """
                ),
                {
                    "transcript_ids": payload.evidence_transcript_ids,
                    "session_id": session_id,
                },
            )
        ).scalars().all()
        if set(evidence_rows) != set(payload.evidence_transcript_ids):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="部分证据发言不存在或不属于该提示的会话",
            )

    coding_id = "cuc" + uuid.uuid4().hex[:12]
    result = await db.execute(
        text(
            """
            INSERT INTO cue_uptake_codes (
                id, push_log_id, coder_role, uptake_code,
                evidence_transcript_ids, coding_reason, coded_by,
                coded_at, created_at, updated_at
            ) VALUES (
                :id, :push_log_id, :coder_role, :uptake_code,
                :evidence_transcript_ids, :coding_reason, :coded_by,
                NOW(), NOW(), NOW()
            )
            ON CONFLICT (push_log_id, coder_role)
            DO UPDATE SET
                uptake_code = EXCLUDED.uptake_code,
                evidence_transcript_ids = EXCLUDED.evidence_transcript_ids,
                coding_reason = EXCLUDED.coding_reason,
                coded_by = EXCLUDED.coded_by,
                coded_at = NOW(),
                updated_at = NOW()
            RETURNING id, push_log_id, coder_role, uptake_code,
                      evidence_transcript_ids, coding_reason, coded_by,
                      coded_at, created_at, updated_at
            """
        ),
        {
            "id": coding_id,
            "push_log_id": push_log_id,
            "coder_role": payload.coder_role,
            "uptake_code": payload.uptake_code,
            "evidence_transcript_ids": payload.evidence_transcript_ids,
            "coding_reason": (payload.coding_reason or "").strip() or None,
            "coded_by": (payload.coded_by or "").strip() or None,
        },
    )
    row = result.mappings().one()
    await db.commit()
    return CueCodingOut.model_validate(dict(row))


@router.delete(
    "/events/{push_log_id}/coding",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_cue_coding(
    push_log_id: str,
    coder_role: str = Query("primary", min_length=1, max_length=20),
    db: AsyncSession = Depends(get_db),
) -> None:
    coder_role = _normalize_coder_role(coder_role)
    result = await db.execute(
        text(
            """
            DELETE FROM cue_uptake_codes
            WHERE push_log_id = :push_log_id AND coder_role = :coder_role
            RETURNING id
            """
        ),
        {"push_log_id": push_log_id, "coder_role": coder_role},
    )
    if not result.first():
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示采纳编码不存在")
    await db.commit()


@router.get("/progress", response_model=CueProgressOut)
async def get_cue_coding_progress(
    condition: str | None = None,
    group_id: str | None = None,
    session_id: str | None = None,
    target_user_id: str | None = None,
    coder_role: str = Query("primary", min_length=1, max_length=20),
    db: AsyncSession = Depends(get_db),
) -> CueProgressOut:
    _validate_optional_filters(condition=condition)
    coder_role = _normalize_coder_role(coder_role)
    where_sql, params = _build_event_filters(
        coder_role=coder_role,
        condition=condition,
        group_id=group_id,
        session_id=session_id,
        target_user_id=target_user_id,
    )
    row = (
        await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(cuc.id)::int AS coded,
                    COUNT(*) FILTER (WHERE cuc.id IS NULL)::int AS uncoded,
                    COUNT(*) FILTER (WHERE cuc.uptake_code = 'not_discussed')::int AS not_discussed,
                    COUNT(*) FILTER (WHERE cuc.uptake_code = 'discussed_not_adopted')::int AS discussed_not_adopted,
                    COUNT(*) FILTER (WHERE cuc.uptake_code = 'discussed_adopted')::int AS discussed_adopted,
                    COUNT(*) FILTER (WHERE cuc.uptake_code = 'uncertain')::int AS uncertain,
                    COUNT(*) FILTER (WHERE cuc.uptake_code = 'not_included')::int AS not_included
                FROM push_logs pl
                JOIN chat_sessions cs ON cs.id = pl.session_id
                JOIN groups g ON g.id = cs.group_id
                LEFT JOIN push_queue pq ON pq.id = pl.queue_id
                LEFT JOIN discussion_states ds ON ds.id = pl.state_id
                LEFT JOIN cue_uptake_codes cuc
                       ON cuc.push_log_id = pl.id
                      AND cuc.coder_role = :coder_role
                WHERE {where_sql}
                """
            ),
            params,
        )
    ).mappings().one()
    total = int(row["total"] or 0)
    coded = int(row["coded"] or 0)
    return CueProgressOut(
        total=total,
        coded=coded,
        uncoded=int(row["uncoded"] or 0),
        completion_rate=(coded / total) if total else 0.0,
        by_code={code: int(row[code] or 0) for code in sorted(VALID_UPTAKE_CODES)},
    )


@router.get("/export")
async def export_cue_codings(
    condition: str | None = None,
    group_id: str | None = None,
    session_id: str | None = None,
    target_user_id: str | None = None,
    coding_status: str | None = None,
    uptake_code: str | None = None,
    coder_role: str = Query("primary", min_length=1, max_length=20),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    _validate_optional_filters(
        condition=condition,
        coding_status=coding_status,
        uptake_code=uptake_code,
    )
    coder_role = _normalize_coder_role(coder_role)
    where_sql, params = _build_event_filters(
        coder_role=coder_role,
        condition=condition,
        group_id=group_id,
        session_id=session_id,
        target_user_id=target_user_id,
        coding_status=coding_status,
        uptake_code=uptake_code,
        keyword=keyword,
    )
    rows = (
        await db.execute(
            text(
                _event_select(where_sql)
                + """
                ORDER BY g.name ASC, cs.created_at ASC,
                         COALESCE(pl.delivered_at, pl.triggered_at) ASC, pl.id ASC
                """
            ),
            params,
        )
    ).mappings().all()

    evidence_ids: list[str] = []
    for row in rows:
        evidence_ids.extend(list(row.get("coding_evidence_transcript_ids") or []))
    evidence_map: dict[str, str] = {}
    if evidence_ids:
        evidence_rows = (
            await db.execute(
                text(
                    """
                    SELECT t.transcript_id,
                           COALESCE(u.name, t.speaker, '未知说话人') AS speaker_name,
                           COALESCE(tc.corrected_text, t.text) AS text
                    FROM speech_transcripts t
                    LEFT JOIN users_info u
                           ON u.id = COALESCE(
                               t.speaker_user_id,
                               t.user_id,
                               NULLIF(BTRIM(t.speaker), '')
                           )
                    LEFT JOIN speech_transcript_corrections tc
                           ON tc.transcript_id = t.transcript_id
                    WHERE t.transcript_id = ANY(:transcript_ids)
                    """
                ),
                {"transcript_ids": list(dict.fromkeys(evidence_ids))},
            )
        ).mappings().all()
        evidence_map = {
            row["transcript_id"]: f"{row['speaker_name']}：{row.get('text') or ''}"
            for row in evidence_rows
        }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "小组ID", "小组", "会话ID", "会话", "实验条件",
        "提示日志ID", "队列ID", "目标成员ID", "目标成员",
        "提示内容", "收到时间", "编码", "证据发言ID",
        "证据发言", "编码理由", "编码者", "编码时间",
    ])
    for raw_row in rows:
        row = dict(raw_row)
        ids = list(row.get("coding_evidence_transcript_ids") or [])
        writer.writerow([
            row["group_id"],
            row["group_name"],
            row["session_id"],
            row.get("session_title") or "",
            row["condition"],
            row["push_log_id"],
            row.get("queue_id") or "",
            row["target_user_id"],
            row["target_user_name"],
            row["push_content"],
            row["received_at"].isoformat() if row.get("received_at") else "",
            row.get("coding_uptake_code") or "",
            ";".join(ids),
            "\n".join(evidence_map.get(item, "") for item in ids),
            row.get("coding_reason") or "",
            row.get("coding_coded_by") or "",
            row["coding_coded_at"].isoformat() if row.get("coding_coded_at") else "",
        ])

    content = "\ufeff" + output.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cue-uptake-codings.csv"'},
    )
