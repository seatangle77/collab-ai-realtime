from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db
from .groups import _get_group_or_404

router = APIRouter(prefix="/api", tags=["sessions"])


class SessionCreate(BaseModel):
    session_title: str
    created_at: datetime | None = None
    last_updated: datetime | None = None
    ended_at: datetime | None = None
    status: str | None = None


class ChatSessionOut(BaseModel):
    id: str
    group_id: str
    created_at: datetime
    last_updated: datetime
    session_title: str
    status: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


@router.post(
    "/groups/{group_id}/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    group_id: str,
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ChatSessionOut:
    """
    在指定群组下创建一次新的会话。
    仅群组内 active 成员可创建。
    """
    await _get_group_or_404(group_id, db)

    membership_result = await db.execute(
        text(
            """
            SELECT 1
            FROM group_memberships
            WHERE group_id = :group_id
              AND user_id = :user_id
              AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    if not membership_result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅群组成员可以创建会话")

    session_id = f"s{uuid.uuid4().hex[:8]}"

    if (
        payload.created_at is None
        and payload.last_updated is None
        and payload.ended_at is None
        and payload.status is None
    ):
        result = await db.execute(
            text(
                """
                INSERT INTO chat_sessions (id, group_id, created_at, last_updated, session_title, status)
                VALUES (:id, :group_id, NOW(), NOW(), :title, 'not_started')
                RETURNING id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
                """
            ),
            {"id": session_id, "group_id": group_id, "title": payload.session_title},
        )
    else:
        created_at = payload.created_at
        last_updated = payload.last_updated or created_at

        if payload.status is not None:
            session_status = payload.status
        elif payload.ended_at is not None:
            session_status = "ended"
        else:
            session_status = "not_started"

        result = await db.execute(
            text(
                """
                INSERT INTO chat_sessions (
                    id,
                    group_id,
                    created_at,
                    last_updated,
                    session_title,
                    status,
                    ended_at
                )
                VALUES (
                    :id,
                    :group_id,
                    COALESCE(:created_at, NOW()),
                    COALESCE(:last_updated, COALESCE(:created_at, NOW())),
                    :title,
                    :status,
                    :ended_at
                )
                RETURNING id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
                """
            ),
            {
                "id": session_id,
                "group_id": group_id,
                "title": payload.session_title,
                "created_at": created_at,
                "last_updated": last_updated,
                "status": session_status,
                "ended_at": payload.ended_at,
            },
        )
    await db.commit()
    row = result.mappings().one()
    return ChatSessionOut.model_validate(dict(row))


@router.get(
    "/groups/{group_id}/sessions",
    response_model=list[ChatSessionOut],
)
async def list_group_sessions(
    group_id: str,
    include_ended: bool = Query(False, description="是否包含已结束的会话"),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[ChatSessionOut]:
    """
    查看某个群组下的会话列表。
    仅群组成员可查看。
    """
    await _get_group_or_404(group_id, db)

    membership_result = await db.execute(
        text(
            """
            SELECT 1
            FROM group_memberships
            WHERE group_id = :group_id
              AND user_id = :user_id
              AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    if not membership_result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅群组成员可以查看会话列表")

    if include_ended:
        query = text(
            """
            SELECT id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
            FROM chat_sessions
            WHERE group_id = :group_id
            ORDER BY last_updated DESC, created_at DESC
            """
        )
    else:
        query = text(
            """
            SELECT id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
            FROM chat_sessions
            WHERE group_id = :group_id
              AND status != 'ended'
            ORDER BY last_updated DESC, created_at DESC
            """
        )
    params = {"group_id": group_id}

    result = await db.execute(query, params)
    rows = result.mappings().all()
    return [ChatSessionOut.model_validate(dict(row)) for row in rows]


class TranscriptOut(BaseModel):
    transcript_id: str
    group_id: str
    session_id: str
    user_id: str | None = None
    speaker: str | None = None
    text: str
    start: Any
    end: Any
    duration: int | None = None
    created_at: datetime


class SessionUpdate(BaseModel):
    session_title: str | None = None
    created_at: datetime | None = None
    last_updated: datetime | None = None
    ended_at: datetime | None = None


async def _get_session_and_group(
    session_id: str,
    db: AsyncSession,
) -> tuple[dict[str, Any], str]:
    result = await db.execute(
        text(
            """
            SELECT id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
            FROM chat_sessions
            WHERE id = :session_id
            """
        ),
        {"session_id": session_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return dict(row), row["group_id"]


async def _ensure_member_of_group(
    group_id: str,
    user_id: str,
    db: AsyncSession,
    forbidden_detail: str,
) -> None:
    membership_result = await db.execute(
        text(
            """
            SELECT 1
            FROM group_memberships
            WHERE group_id = :group_id
              AND user_id = :user_id
              AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": user_id},
    )
    if not membership_result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=forbidden_detail)


@router.get(
    "/sessions/{session_id}/transcripts",
    response_model=list[TranscriptOut],
)
async def list_session_transcripts(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> list[TranscriptOut]:
    """
    查看某次会话下的全部语音转写记录。
    仅该会话所属群组的成员可以访问。
    """
    session_result = await db.execute(
        text(
            """
            SELECT group_id
            FROM chat_sessions
            WHERE id = :session_id
            """
        ),
        {"session_id": session_id},
    )
    session_row = session_result.mappings().first()
    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    group_id = session_row["group_id"]
    await _get_group_or_404(group_id, db)

    membership_result = await db.execute(
        text(
            """
            SELECT 1
            FROM group_memberships
            WHERE group_id = :group_id
              AND user_id = :user_id
              AND status = 'active'
            """
        ),
        {"group_id": group_id, "user_id": current_user["id"]},
    )
    if not membership_result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅群组成员可以查看会话转写记录")

    result = await db.execute(
        text(
            """
            SELECT
                transcript_id,
                group_id,
                session_id,
                user_id,
                speaker,
                text,
                start,
                "end",
                duration,
                created_at
            FROM speech_transcripts
            WHERE session_id = :session_id
            ORDER BY start ASC
            """
        ),
        {"session_id": session_id},
    )
    rows = result.mappings().all()
    return [TranscriptOut.model_validate(dict(row)) for row in rows]


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionOut,
)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ChatSessionOut:
    """
    更新会话信息。
    - 始终允许更新标题；
    - 仅「未开始」的会话可以修改时间字段（created_at / last_updated / ended_at）；
    - 若未显式传入时间字段，则自动将 last_updated 刷新为 NOW()。
    """
    session_row, group_id = await _get_session_and_group(session_id, db)
    await _get_group_or_404(group_id, db)
    await _ensure_member_of_group(
        group_id,
        current_user["id"],
        db,
        forbidden_detail="仅群组成员可以修改会话信息",
    )

    if (
        payload.session_title is None
        and payload.created_at is None
        and payload.last_updated is None
        and payload.ended_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供会话标题或时间字段之一",
        )

    incoming_time_fields = any(
        value is not None for value in (payload.created_at, payload.last_updated, payload.ended_at)
    )

    if incoming_time_fields:
        # 仅未开始（not_started）的会话允许修改时间字段
        if session_row["status"] != "not_started":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="仅未开始的会话可以修改时间",
            )

        result = await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET
                    session_title = COALESCE(:title, session_title),
                    created_at = COALESCE(:created_at, created_at),
                    last_updated = COALESCE(:last_updated, last_updated),
                    ended_at = COALESCE(:ended_at, ended_at)
                WHERE id = :session_id
                RETURNING id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
                """
            ),
            {
                "session_id": session_id,
                "title": payload.session_title,
                "created_at": payload.created_at,
                "last_updated": payload.last_updated,
                "ended_at": payload.ended_at,
            },
        )
    else:
        new_title = payload.session_title or session_row["session_title"]
        result = await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET session_title = :title,
                    last_updated = NOW()
                WHERE id = :session_id
                RETURNING id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
                """
            ),
            {"session_id": session_id, "title": new_title},
        )
    await db.commit()
    row = result.mappings().one()
    return ChatSessionOut.model_validate(dict(row))


@router.post(
    "/sessions/{session_id}/start",
    response_model=ChatSessionOut,
)
async def start_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ChatSessionOut:
    """
    发起讨论：将会话状态从 not_started 改为 ongoing。
    同一群组内只能有一个 ongoing 会话。
    """
    session_row, group_id = await _get_session_and_group(session_id, db)
    await _get_group_or_404(group_id, db)
    await _ensure_member_of_group(
        group_id,
        current_user["id"],
        db,
        forbidden_detail="仅群组成员可以发起会话",
    )

    if session_row["status"] != "not_started":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅未开始的会话可以发起",
        )

    ongoing_result = await db.execute(
        text(
            """
            SELECT 1 FROM chat_sessions
            WHERE group_id = :group_id
              AND status = 'ongoing'
              AND id != :session_id
            """
        ),
        {"group_id": group_id, "session_id": session_id},
    )
    if ongoing_result.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该群组已有进行中的会话",
        )

    result = await db.execute(
        text(
            """
            UPDATE chat_sessions
            SET status = 'ongoing',
                started_at = NOW(),
                last_updated = NOW()
            WHERE id = :session_id
            RETURNING id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
            """
        ),
        {"session_id": session_id},
    )
    await db.commit()
    row = result.mappings().one()
    return ChatSessionOut.model_validate(dict(row))


@router.post(
    "/sessions/{session_id}/end",
    response_model=ChatSessionOut,
)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> ChatSessionOut:
    """
    标记会话为已结束，设置 status = 'ended', ended_at = NOW()。
    仅所属群组成员可操作。
    """
    session_row, group_id = await _get_session_and_group(session_id, db)
    await _get_group_or_404(group_id, db)
    await _ensure_member_of_group(
        group_id,
        current_user["id"],
        db,
        forbidden_detail="仅群组成员可以结束会话",
    )

    result = await db.execute(
        text(
            """
            UPDATE chat_sessions
            SET status = 'ended',
                ended_at = NOW(),
                last_updated = NOW()
            WHERE id = :session_id
            RETURNING id, group_id, created_at, last_updated, session_title, status, started_at, ended_at
            """
        ),
        {"session_id": session_id},
    )
    await db.commit()
    row = result.mappings().one()
    return ChatSessionOut.model_validate(dict(row))
