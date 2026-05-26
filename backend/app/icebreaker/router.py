from __future__ import annotations

import logging
from typing import Any, Mapping

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api_model import ApiModel
from ..auth import get_current_user
from ..db import get_db
from .ai import evaluate_icebreaker_story
from .asr import (
    IcebreakerASRUnavailable,
    IcebreakerAudioDecodeError,
    transcribe_icebreaker_audio,
)
from .voice_sample import add_icebreaker_voice_sample

router = APIRouter(prefix="/api/icebreaker", tags=["icebreaker"])
logger = logging.getLogger(__name__)


class IcebreakerMember(ApiModel):
    user_id: str
    user_name: str | None = None


class IcebreakerStoryTurn(ApiModel):
    user_id: str
    user_name: str | None = None
    round: int = Field(ge=1, le=10)
    turn_index: int = Field(ge=1, le=30)
    text: str = Field(min_length=1, max_length=500)


class IcebreakerEvaluateRequest(ApiModel):
    group_id: str
    story_opening: str = Field(default="", max_length=500)
    members: list[IcebreakerMember] = Field(default_factory=list)
    turns: list[IcebreakerStoryTurn] = Field(min_length=1, max_length=30)


class IcebreakerEvaluateResponse(ApiModel):
    polished_story: str = ""
    score: int
    comment: str
    mvp_user_id: str
    mvp_title: str
    mvp_reason: str


class IcebreakerTranscribeResponse(ApiModel):
    text: str


class IcebreakerVoiceSampleResponse(ApiModel):
    text: str
    voice_sample_added: bool = False
    sample_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


async def _ensure_group_member(group_id: str, user_id: str, db: AsyncSession) -> None:
    result = await db.execute(
        text(
            """
            SELECT 1
            FROM group_memberships gm
            JOIN groups g ON g.id = gm.group_id
            WHERE gm.group_id = :group_id
              AND gm.user_id = :user_id
              AND gm.status = 'active'
              AND g.is_active = TRUE
            """
        ),
        {"group_id": group_id, "user_id": user_id},
    )
    if not result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该小组破冰")


async def _get_active_group_member_ids(group_id: str, db: AsyncSession) -> set[str]:
    result = await db.execute(
        text(
            """
            SELECT user_id
            FROM group_memberships
            WHERE group_id = :group_id
              AND status = 'active'
            """
        ),
        {"group_id": group_id},
    )
    return {str(row["user_id"]) for row in result.mappings().all()}


async def _get_active_group_members(group_id: str, db: AsyncSession) -> dict[str, str]:
    result = await db.execute(
        text(
            """
            SELECT gm.user_id, ui.name AS user_name
            FROM group_memberships gm
            LEFT JOIN users_info ui ON ui.id = gm.user_id
            WHERE gm.group_id = :group_id
              AND gm.status = 'active'
            """
        ),
        {"group_id": group_id},
    )
    members: dict[str, str] = {}
    for row in result.mappings().all():
        user_id = str(row["user_id"])
        members[user_id] = str(row.get("user_name") or user_id)
    return members


@router.post("/transcribe", response_model=IcebreakerTranscribeResponse)
async def transcribe_icebreaker_turn(
    group_id: str = Form(...),
    user_id: str = Form(...),
    round: int = Form(...),
    turn_index: int = Form(...),
    mime_type: str = Form(...),
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> IcebreakerTranscribeResponse:
    """
    破冰单段录音临时转写。
    不入库，不写 speech_transcripts，不接正式讨论 session。
    """
    current_user_id = str(current_user["id"])
    logger.info(
        "[IcebreakerAPI] transcribe request group_id=%s user_id=%s round=%s turn_index=%s mime_type=%s",
        group_id,
        user_id,
        round,
        turn_index,
        mime_type,
    )
    await _ensure_group_member(group_id, current_user_id, db)
    active_member_ids = await _get_active_group_member_ids(group_id, db)
    if user_id not in active_member_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="破冰录音说话人不在该小组内")

    audio_bytes = await audio.read()
    logger.info(
        "[IcebreakerAPI] transcribe audio_received group_id=%s user_id=%s turn_index=%s bytes=%d",
        group_id,
        user_id,
        turn_index,
        len(audio_bytes),
    )
    try:
        text_value = await transcribe_icebreaker_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            turn_id=f"{group_id}-{user_id}-r{round}-t{turn_index}",
        )
    except IcebreakerAudioDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="破冰录音解码失败") from exc
    except IcebreakerASRUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="破冰语音识别暂不可用") from exc

    logger.info(
        "[IcebreakerAPI] transcribe response group_id=%s user_id=%s turn_index=%s text_len=%d text_preview=%s",
        group_id,
        user_id,
        turn_index,
        len(text_value),
        text_value[:80],
    )
    return IcebreakerTranscribeResponse(text=text_value)


@router.post("/voice-sample", response_model=IcebreakerVoiceSampleResponse)
async def upload_icebreaker_voice_sample(
    group_id: str = Form(...),
    user_id: str = Form(...),
    source: str = Form(...),
    mime_type: str = Form(...),
    audio: UploadFile = File(...),
    question_index: int | None = Form(None),
    round: int | None = Form(None),
    turn_index: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> IcebreakerVoiceSampleResponse:
    """
    破冰专用声纹样本采集：转写录音，并将合格音频追加到现有个人声纹样本。
    """
    current_user_id = str(current_user["id"])
    normalized_source = source.strip().lower()
    if normalized_source not in {"intro", "story"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的破冰录音来源")

    await _ensure_group_member(group_id, current_user_id, db)
    active_members = await _get_active_group_members(group_id, db)
    if user_id not in active_members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="破冰录音说话人不在该小组内")

    audio_bytes = await audio.read()
    logger.info(
        "[IcebreakerAPI] voice_sample request group_id=%s user_id=%s source=%s question_index=%s round=%s turn_index=%s bytes=%d",
        group_id,
        user_id,
        normalized_source,
        question_index,
        round,
        turn_index,
        len(audio_bytes),
    )

    try:
        text_value = await transcribe_icebreaker_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            turn_id=f"{group_id}-{user_id}-{normalized_source}-q{question_index or 0}-r{round or 0}-t{turn_index or 0}",
        )
    except IcebreakerAudioDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="破冰录音解码失败") from exc
    except IcebreakerASRUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="破冰语音识别暂不可用") from exc

    sample_result = await add_icebreaker_voice_sample(
        db=db,
        user_id=user_id,
        group_id=group_id,
        source=normalized_source,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        text_value=text_value,
        question_index=question_index,
        round_no=round,
        turn_index=turn_index,
    )
    warnings = list(sample_result.warnings)

    logger.info(
        "[IcebreakerAPI] voice_sample response group_id=%s user_id=%s added=%s warnings=%s text_preview=%s",
        group_id,
        user_id,
        sample_result.voice_sample_added,
        warnings,
        text_value[:80],
    )
    return IcebreakerVoiceSampleResponse(
        text=text_value,
        voice_sample_added=sample_result.voice_sample_added,
        sample_url=sample_result.sample_url,
        warnings=warnings,
    )


@router.post("/evaluate", response_model=IcebreakerEvaluateResponse)
async def evaluate_icebreaker(
    payload: IcebreakerEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> IcebreakerEvaluateResponse:
    """
    破冰故事接龙 AI 评价。
    只消费前端提交的临时文本，不入库，不进入核心讨论分析链路。
    """
    current_user_id = str(current_user["id"])
    logger.info(
        "[IcebreakerAPI] evaluate request group_id=%s requester=%s members=%d turns=%d story_len=%d",
        payload.group_id,
        current_user_id,
        len(payload.members),
        len(payload.turns),
        len(payload.story_opening or ""),
    )
    await _ensure_group_member(payload.group_id, current_user_id, db)

    active_member_ids = await _get_active_group_member_ids(payload.group_id, db)
    turn_user_ids = {turn.user_id for turn in payload.turns}
    if not turn_user_ids.issubset(active_member_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="接龙记录包含非本组成员")

    member_items = [member.model_dump() for member in payload.members]
    if not member_items:
        member_items = [{"user_id": uid, "user_name": uid} for uid in sorted(active_member_ids)]

    result = await evaluate_icebreaker_story(
        story_opening=payload.story_opening,
        members=member_items,
        turns=[turn.model_dump() for turn in payload.turns],
    )
    logger.info(
        "[IcebreakerAPI] evaluate response group_id=%s score=%s mvp_user_id=%s title=%s comment=%s",
        payload.group_id,
        result.get("score"),
        result.get("mvp_user_id"),
        result.get("mvp_title"),
        result.get("comment"),
    )
    return IcebreakerEvaluateResponse(**result)
