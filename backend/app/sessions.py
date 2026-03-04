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


class ChatSessionOut(BaseModel):
    id: str
    group_id: str
    created_at: datetime
    last_updated: datetime
    session_title: str


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

    # 当前用户是否是群成员（active）
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

    result = await db.execute(
        text(
            """
            INSERT INTO chat_sessions (id, group_id, created_at, last_updated, session_title)
            VALUES (:id, :group_id, NOW(), NOW(), :title)
            RETURNING id, group_id, created_at, last_updated, session_title
            """
        ),
        {"id": session_id, "group_id": group_id, "title": payload.session_title},
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
            SELECT id, group_id, created_at, last_updated, session_title
            FROM chat_sessions
            WHERE group_id = :group_id
            ORDER BY last_updated DESC, created_at DESC
            """
        )
        params = {"group_id": group_id}
    else:
        query = text(
            """
            SELECT id, group_id, created_at, last_updated, session_title
            FROM chat_sessions
            WHERE group_id = :group_id
              AND (is_active = TRUE OR is_active IS NULL)
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
    session_title: str


async def _get_session_and_group(
    session_id: str,
    db: AsyncSession,
) -> tuple[dict[str, Any], str]:
    result = await db.execute(
        text(
            """
            SELECT id, group_id, created_at, last_updated, session_title, is_active, ended_at
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
    # 找到会话所属的 group
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
    更新会话标题，并刷新 last_updated。
    仅所属群组成员可操作。
    """
    session_row, group_id = await _get_session_and_group(session_id, db)
    await _get_group_or_404(group_id, db)
    await _ensure_member_of_group(
        group_id,
        current_user["id"],
        db,
        forbidden_detail="仅群组成员可以修改会话信息",
    )

    result = await db.execute(
        text(
            """
            UPDATE chat_sessions
            SET session_title = :title,
                last_updated = NOW()
            WHERE id = :session_id
            RETURNING id, group_id, created_at, last_updated, session_title
            """
        ),
        {"session_id": session_id, "title": payload.session_title},
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
    标记会话为已结束，设置 is_active = FALSE, ended_at = NOW()。
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
            SET is_active = FALSE,
                ended_at = NOW(),
                last_updated = NOW()
            WHERE id = :session_id
            RETURNING id, group_id, created_at, last_updated, session_title
            """
        ),
        {"session_id": session_id},
    )
    await db.commit()
    row = result.mappings().one()
    return ChatSessionOut.model_validate(dict(row))

