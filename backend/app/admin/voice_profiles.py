from __future__ import annotations

from typing import Any, Mapping
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config_voice import VOICE_AUDIO_BASE_DIR, VOICE_AUDIO_PUBLIC_BASE_URL
from ..db import get_db
from ..voice_profiles import ALLOWED_AUDIO_CONTENT_TYPES, VoiceProfileOut, _row_to_profile
from .deps import require_admin
from .schemas import Page, PageMeta


router = APIRouter(
    prefix="/api/admin/voice-profiles",
    tags=["admin-voice-profiles"],
    dependencies=[Depends(require_admin)],
)


class AdminVoiceProfileSummary(BaseModel):
    id: str
    user_id: str
    user_name: str | None = None
    user_email: str | None = None
    primary_group_id: str | None = None
    primary_group_name: str | None = None
    sample_count: int
    has_embedding: bool
    created_at: Any


@router.get("/", response_model=Page[AdminVoiceProfileSummary])
async def list_voice_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str | None = None,
    has_samples: bool | None = None,
    has_embedding: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> Page[AdminVoiceProfileSummary]:
    offset = (page - 1) * page_size

    where_clauses: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    if user_id:
        where_clauses.append("user_id = :user_id")
        params["user_id"] = user_id

    if has_samples is True:
        where_clauses.append("jsonb_array_length(sample_audio_urls) > 0")
    elif has_samples is False:
        where_clauses.append("jsonb_array_length(sample_audio_urls) = 0")

    if has_embedding is True:
        where_clauses.append("voice_embedding IS NOT NULL")
    elif has_embedding is False:
        where_clauses.append("voice_embedding IS NULL")

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(
            f"""
            SELECT COUNT(*) AS cnt
            FROM user_voice_profiles p
            WHERE {where_sql}
            """
        ),
        params,
    )
    total = count_result.scalar_one()

    query = text(
        f"""
        SELECT
          p.id,
          p.user_id,
          u.name AS user_name,
          u.email AS user_email,
          g.group_id AS primary_group_id,
          g.group_name AS primary_group_name,
          COALESCE(jsonb_array_length(p.sample_audio_urls), 0) AS sample_count,
          (p.voice_embedding IS NOT NULL) AS has_embedding,
          p.created_at
        FROM user_voice_profiles p
        LEFT JOIN users_info u ON u.id = p.user_id
        LEFT JOIN LATERAL (
          SELECT gm.group_id, grp.name AS group_name
          FROM group_memberships gm
          JOIN groups grp ON grp.id = gm.group_id
          WHERE gm.user_id = p.user_id
            AND gm.status = 'active'
          ORDER BY gm.created_at ASC
          LIMIT 1
        ) g ON TRUE
        WHERE {where_sql}
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    params_with_page = dict(params)
    params_with_page["limit"] = page_size
    params_with_page["offset"] = offset

    result = await db.execute(query, params_with_page)
    rows = result.mappings().all()

    items: list[AdminVoiceProfileSummary] = []
    for row in rows:
        items.append(
            AdminVoiceProfileSummary(
                id=row["id"],
                user_id=row["user_id"],
                user_name=row.get("user_name"),
                user_email=row.get("user_email"),
                primary_group_id=row.get("primary_group_id"),
                primary_group_name=row.get("primary_group_name"),
                sample_count=row["sample_count"] or 0,
                has_embedding=bool(row["has_embedding"]),
                created_at=row["created_at"],
            )
        )

    return Page[AdminVoiceProfileSummary](
        items=items,
        meta=PageMeta(total=total, page=page, page_size=page_size),
    )


class AdminVoiceProfileDetail(BaseModel):
    profile: VoiceProfileOut
    user_name: str | None = None
    user_email: str | None = None
    primary_group_id: str | None = None
    primary_group_name: str | None = None


class AdminUploadAudioResponse(BaseModel):
    url: str


@router.get(
    "/{profile_id}",
    response_model=AdminVoiceProfileDetail,
)
async def get_voice_profile_detail(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminVoiceProfileDetail:
    result = await db.execute(
        text(
            """
            SELECT
              p.id,
              p.user_id,
              p.voice_embedding,
              p.sample_audio_urls,
              p.created_at,
              u.name AS user_name,
              u.email AS user_email,
              g.group_id AS primary_group_id,
              g.group_name AS primary_group_name
            FROM user_voice_profiles p
            LEFT JOIN users_info u ON u.id = p.user_id
            LEFT JOIN LATERAL (
              SELECT gm.group_id, grp.name AS group_name
              FROM group_memberships gm
              JOIN groups grp ON grp.id = gm.group_id
              WHERE gm.user_id = p.user_id
                AND gm.status = 'active'
              ORDER BY gm.created_at ASC
              LIMIT 1
            ) g ON TRUE
            WHERE p.id = :id
            """
        ),
        {"id": profile_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="声纹配置不存在",
        )
    profile = _row_to_profile(row)
    return AdminVoiceProfileDetail(
        profile=profile,
        user_name=row.get("user_name"),
        user_email=row.get("user_email"),
        primary_group_id=row.get("primary_group_id"),
        primary_group_name=row.get("primary_group_name"),
    )


class AdminUpdateSamplesRequest(BaseModel):
    sample_audio_urls: list[str]


@router.put(
    "/{profile_id}/samples",
    response_model=VoiceProfileOut,
)
async def admin_update_samples(
    profile_id: str,
    payload: AdminUpdateSamplesRequest,
    db: AsyncSession = Depends(get_db),
) -> VoiceProfileOut:
    max_samples = 5
    if len(payload.sample_audio_urls) > max_samples:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"最多支持 {max_samples} 条语音样本",
        )
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
            "id": profile_id,
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
    "/{profile_id}/generate-embedding",
    response_model=VoiceProfileOut,
)
async def admin_generate_embedding(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> VoiceProfileOut:
    result = await db.execute(
        text(
            """
            SELECT id, user_id, voice_embedding, sample_audio_urls, created_at
            FROM user_voice_profiles
            WHERE id = :id
            """
        ),
        {"id": profile_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="声纹配置不存在",
        )

    profile = _row_to_profile(row)
    if not profile.sample_audio_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该声纹配置尚无任何语音样本，无法生成声纹",
        )

    placeholder_embedding: Mapping[str, Any] = {
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "note": "placeholder_embedding, replace with real voice embedding later",
    }

    result2 = await db.execute(
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
    row2 = result2.mappings().first()
    if not row2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="声纹配置不存在",
        )

    await db.commit()
    return _row_to_profile(row2)


@router.post(
    "/{profile_id}/upload-audio",
    response_model=AdminUploadAudioResponse,
)
async def admin_upload_audio_sample(
    profile_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> AdminUploadAudioResponse:
    """
    管理端为指定声纹配置上传一段音频，写入挂载目录并返回可访问的 URL。
    不直接修改样本列表，由前端在拿到 URL 后调用 /samples 接口进行保存。
    """
    result = await db.execute(
        text(
            """
            SELECT id, user_id, voice_embedding, sample_audio_urls, created_at
            FROM user_voice_profiles
            WHERE id = :id
            """
        ),
        {"id": profile_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="声纹配置不存在",
        )

    profile = _row_to_profile(row)

    if len(profile.sample_audio_urls) >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="最多支持 5 条语音样本",
        )

    if file.content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不支持的音频格式",
        )

    ext = ".webm"
    if file.content_type == "audio/mpeg":
        ext = ".mp3"
    elif file.content_type == "audio/wav":
        ext = ".wav"
    elif file.content_type == "audio/ogg":
        ext = ".ogg"

    filename = f"{profile.user_id}-{datetime.now(timezone.utc).timestamp():.0f}{ext}"

    base_dir: Path = VOICE_AUDIO_BASE_DIR
    dest_dir = base_dir / profile.user_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    try:
        with dest_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        file.file.close()

    public_url = f"{VOICE_AUDIO_PUBLIC_BASE_URL}/{profile.user_id}/{filename}"
    return AdminUploadAudioResponse(url=public_url)


