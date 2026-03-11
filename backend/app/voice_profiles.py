from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db


router = APIRouter(prefix="/api/voice-profile", tags=["voice-profile"])


class VoiceProfileOut(BaseModel):
    id: str
    user_id: str
    sample_audio_urls: list[str] = Field(default_factory=list)
    created_at: datetime
    voice_embedding: dict[str, Any] | None = None


class UpdateSamplesRequest(BaseModel):
    sample_audio_urls: list[str]

    @field_validator("sample_audio_urls")
    @classmethod
    def validate_sample_audio_urls(cls, v: list[str]) -> list[str]:
        max_samples = 10
        if len(v) > max_samples:
            raise ValueError(f"最多支持 {max_samples} 条语音样本")
        return v


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row_to_profile(row: Mapping[str, Any]) -> VoiceProfileOut:
    urls = row.get("sample_audio_urls") or []
    # asyncpg 通常会把 jsonb 解为 Python 对象，这里兜底为 list[str]
    if isinstance(urls, str):
        try:
            urls = json.loads(urls)
        except json.JSONDecodeError:
            urls = []
    if not isinstance(urls, list):
        urls = []

    payload: dict[str, Any] = {
        "id": row["id"],
        "user_id": row["user_id"],
        "sample_audio_urls": urls,
        "created_at": row["created_at"],
        "voice_embedding": row.get("voice_embedding"),
    }
    return VoiceProfileOut.model_validate(payload)


async def _get_or_create_profile(
    user_id: str,
    db: AsyncSession,
) -> VoiceProfileOut:
    result = await db.execute(
        text(
            """
            SELECT id, user_id, voice_embedding, sample_audio_urls, created_at
            FROM user_voice_profiles
            WHERE user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row:
        return _row_to_profile(row)

    profile_id = f"vp{uuid.uuid4().hex[:12]}"
    now_utc = _utc_now_naive()

    insert_result = await db.execute(
        text(
            """
            INSERT INTO user_voice_profiles (id, user_id, sample_audio_urls, created_at)
            VALUES (:id, :user_id, CAST(:sample_audio_urls AS jsonb), :created_at)
            RETURNING id, user_id, voice_embedding, sample_audio_urls, created_at
            """
        ),
        {
            "id": profile_id,
            "user_id": user_id,
            "sample_audio_urls": json.dumps([]),
            "created_at": now_utc,
        },
    )
    await db.commit()
    new_row = insert_result.mappings().one()
    return _row_to_profile(new_row)


@router.get(
    "/me",
    response_model=VoiceProfileOut,
)
async def get_my_voice_profile(
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VoiceProfileOut:
    """
    获取当前登录用户的声纹配置；如果不存在则自动初始化一条空配置。
    """
    user_id = current_user["id"]
    profile = await _get_or_create_profile(user_id=user_id, db=db)
    return profile


@router.put(
    "/me/samples",
    response_model=VoiceProfileOut,
)
async def update_my_voice_samples(
    payload: UpdateSamplesRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VoiceProfileOut:
    """
    更新当前用户的语音样本 URL 列表。
    默认行为为全量覆盖；如需增量追加可在上层前端自行合并后再提交。
    """
    user_id = current_user["id"]
    profile = await _get_or_create_profile(user_id=user_id, db=db)

    result = await db.execute(
        text(
            """
            UPDATE user_voice_profiles
            SET sample_audio_urls = CAST(:sample_audio_urls AS jsonb)
            WHERE id = :id
            RETURNING id, user_id, voice_embedding, sample_audio_urls, created_at
            """
        ),
        {
            "id": profile.id,
            "sample_audio_urls": json.dumps(payload.sample_audio_urls),
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="声纹配置不存在",
        )

    await db.commit()
    return _row_to_profile(row)


@router.post(
    "/me/generate-embedding",
    response_model=VoiceProfileOut,
    status_code=status.HTTP_200_OK,
)
async def generate_my_voice_embedding(
    current_user: Mapping[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VoiceProfileOut:
    """
    根据当前样本触发声纹向量生成。
    目前为占位实现：写入一个包含生成时间的占位 JSON，后续可替换为真实模型推理。
    """
    user_id = current_user["id"]
    profile = await _get_or_create_profile(user_id=user_id, db=db)

    if not profile.sample_audio_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先上传至少一条语音样本后再生成声纹",
        )

    placeholder_embedding = {
        "generated_at": _utc_now_naive().isoformat(),
        # 这里故意使用纯 ASCII 文本，避免在 SQL_ASCII 编码的数据库中触发 UTF8/SQL_ASCII 转换错误。
        "note": "placeholder_embedding, replace with real voice embedding later",
    }

    result = await db.execute(
        text(
            """
            UPDATE user_voice_profiles
            SET voice_embedding = CAST(:voice_embedding AS jsonb)
            WHERE id = :id
            RETURNING id, user_id, voice_embedding, sample_audio_urls, created_at
            """
        ),
        {
            "id": profile.id,
            "voice_embedding": json.dumps(placeholder_embedding),
        },
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="声纹配置不存在",
        )

    await db.commit()
    return _row_to_profile(row)

