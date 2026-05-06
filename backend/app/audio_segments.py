from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db, get_sessionmaker

router = APIRouter(prefix="/api", tags=["offline-audio-segments"])

MAX_OFFLINE_AUDIO_BYTES = 20 * 1024 * 1024
ALLOWED_MIME_TYPES = ("audio/webm", "audio/aac", "audio/mp4")


class OfflineAudioDecodeError(RuntimeError):
    pass


class OfflineRecognitionUnavailable(RuntimeError):
    pass


def _normalize_mime_type(mime_type: str) -> str:
    return mime_type.split(";", 1)[0].strip().lower()


def _ffmpeg_input_format(mime_type: str) -> str:
    if mime_type == "audio/webm":
        return "webm"
    if mime_type == "audio/aac":
        return "aac"
    if mime_type == "audio/mp4":
        return "mp4"
    raise OfflineAudioDecodeError("unsupported_audio")


def decode_offline_audio_to_pcm(audio_bytes: bytes, mime_type: str) -> bytes:
    """Decode a complete offline audio segment to 16kHz mono s16le PCM."""
    input_format = _ffmpeg_input_format(mime_type)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                input_format,
                "-i",
                "pipe:0",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OfflineAudioDecodeError("ffmpeg_missing") from exc
    except subprocess.TimeoutExpired as exc:
        raise OfflineAudioDecodeError("decode_timeout") from exc

    if result.returncode != 0 or not result.stdout:
        raise OfflineAudioDecodeError("decode_failed")
    return result.stdout


async def recognize_offline_audio_segment(
    pcm_bytes: bytes,
    *,
    session_id: str,
    user_id: str,
    segment_id: str,
) -> str:
    """
    Offline ASR hook.

    The current production stack only has realtime Tencent ASR. Keep the hook
    explicit so tests and future Tencent file-ASR integration can replace it
    without pretending that decode success equals transcript success.
    """
    if os.getenv("OFFLINE_AUDIO_TRANSCRIPT_PLACEHOLDER", "").strip().lower() in {"1", "true", "yes"}:
        return f"（补传）已收到离线录音段 {segment_id}，待接入离线 ASR 后替换为真实转写"
    raise OfflineRecognitionUnavailable("offline_recognition_unavailable")


async def ensure_offline_audio_segments_table() -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS offline_audio_segments (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    segment_id TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    started_at TIMESTAMP NULL,
                    ended_at TIMESTAMP NULL,
                    status TEXT NOT NULL,
                    error_reason TEXT NULL,
                    transcript_id TEXT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (session_id, user_id, segment_id)
                )
                """
            )
        )
        await db.commit()


def _parse_client_datetime(value: str, field: str) -> datetime:
    try:
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field} 格式不正确") from exc

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def _get_session_for_upload(session_id: str, db: AsyncSession) -> Mapping[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT id, group_id, status
            FROM chat_sessions
            WHERE id = :session_id
            """
        ),
        {"session_id": session_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if row["status"] != "ongoing":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话不是进行中，不能补传录音")
    return row


async def _ensure_member(group_id: str, user_id: str, db: AsyncSession) -> None:
    result = await db.execute(
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
    if not result.first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该会话")


async def _find_existing_segment(
    session_id: str,
    user_id: str,
    segment_id: str,
    db: AsyncSession,
) -> Mapping[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT id, status, transcript_id, error_reason
            FROM offline_audio_segments
            WHERE session_id = :session_id
              AND user_id = :user_id
              AND segment_id = :segment_id
            """
        ),
        {"session_id": session_id, "user_id": user_id, "segment_id": segment_id},
    )
    return result.mappings().first()


async def _mark_segment_failed(db: AsyncSession, segment_row_id: str, reason: str) -> None:
    await db.execute(
        text(
            """
            UPDATE offline_audio_segments
            SET status = 'failed',
                error_reason = :reason,
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {"id": segment_row_id, "reason": reason},
    )
    await db.commit()


@router.post("/sessions/{session_id}/audio-segments", response_model=None)
async def upload_offline_audio_segment(
    session_id: str,
    segment_id: str = Form(...),
    started_at: str = Form(...),
    ended_at: str = Form(...),
    mime_type: str = Form(...),
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    normalized_mime = _normalize_mime_type(mime_type)
    if normalized_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的音频格式")

    start_dt = _parse_client_datetime(started_at, "started_at")
    end_dt = _parse_client_datetime(ended_at, "ended_at")
    if end_dt < start_dt:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ended_at 不能早于 started_at")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="音频文件不能为空")
    if len(audio_bytes) > MAX_OFFLINE_AUDIO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="音频文件过大")

    session_row = await _get_session_for_upload(session_id, db)
    user_id = str(current_user["id"])
    await _ensure_member(session_row["group_id"], user_id, db)

    existing = await _find_existing_segment(session_id, user_id, segment_id, db)
    if existing:
        if existing["status"] == "processed":
            return {
                "status": "processed",
                "segment_id": segment_id,
                "transcript_id": existing["transcript_id"],
                "duplicate": True,
            }
        if existing["status"] == "processing":
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={"status": "processing", "segment_id": segment_id},
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该录音段已处理失败，请使用新的 segment_id 重试")

    row_id = f"oas{uuid.uuid4().hex[:8]}"
    try:
        await db.execute(
            text(
                """
                INSERT INTO offline_audio_segments (
                    id, session_id, user_id, segment_id, mime_type,
                    started_at, ended_at, status, created_at, updated_at
                )
                VALUES (
                    :id, :session_id, :user_id, :segment_id, :mime_type,
                    :started_at, :ended_at, 'processing', NOW(), NOW()
                )
                """
            ),
            {
                "id": row_id,
                "session_id": session_id,
                "user_id": user_id,
                "segment_id": segment_id,
                "mime_type": normalized_mime,
                "started_at": start_dt,
                "ended_at": end_dt,
            },
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "processing", "segment_id": segment_id},
        )

    try:
        pcm_bytes = decode_offline_audio_to_pcm(audio_bytes, normalized_mime)
    except OfflineAudioDecodeError as exc:
        await _mark_segment_failed(db, row_id, str(exc))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="离线录音解码失败") from exc

    try:
        transcript_text = await recognize_offline_audio_segment(
            pcm_bytes,
            session_id=session_id,
            user_id=user_id,
            segment_id=segment_id,
        )
    except OfflineRecognitionUnavailable as exc:
        await _mark_segment_failed(db, row_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="离线语音识别暂不可用") from exc

    from .transcript_realtime import insert_speech_transcript_and_broadcast

    transcript = await insert_speech_transcript_and_broadcast(
        session_id,
        text=transcript_text,
        speaker=user_id,
        user_id=user_id,
        start=start_dt,
        end=end_dt,
        duration=(end_dt - start_dt).total_seconds(),
        confidence=None,
    )
    if not transcript:
        await _mark_segment_failed(db, row_id, "transcript_insert_failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="补传转写写入失败")

    transcript_id = transcript.get("transcript_id")
    await db.execute(
        text(
            """
            UPDATE offline_audio_segments
            SET status = 'processed',
                transcript_id = :transcript_id,
                error_reason = NULL,
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {"id": row_id, "transcript_id": transcript_id},
    )
    await db.commit()

    return {
        "status": "processed",
        "segment_id": segment_id,
        "transcript_id": transcript_id,
        "duplicate": False,
    }
