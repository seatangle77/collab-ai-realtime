"""
实时转写：写入 speech_transcripts 后按 session 广播 WebSocket transcript。
供后续音频/ASR 模块调用；可选在开发时通过环境变量在 audio_chunk 后插入占位记录。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import DBNotConfiguredError, get_sessionmaker


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _row_to_ws_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """与 GET /api/sessions/{id}/transcripts 单条结构一致，时间转 ISO 字符串便于前端 JSON。"""
    d = dict(row)
    out: dict[str, Any] = {}
    for key in (
        "transcript_id",
        "group_id",
        "session_id",
        "user_id",
        "speaker",
        "text",
        "start",
        "end",
        "duration",
        "confidence",
        "created_at",
    ):
        if key not in d:
            continue
        v = d[key]
        if isinstance(v, datetime):
            out[key] = v.isoformat()
        else:
            out[key] = v
    return out


async def insert_speech_transcript_and_broadcast(
    session_id: str,
    *,
    text: str,
    speaker: str | None = None,
    user_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    duration: float | None = None,
    confidence: float | None = None,
    audio_url: str | None = None,
) -> dict[str, Any] | None:
    """
    插入一条转写并广播 transcript。失败时返回 None（不写库、不广播）。
    """
    if not text or not text.strip():
        return None

    try:
        session_factory = get_sessionmaker()
    except DBNotConfiguredError:
        return None

    async with session_factory() as db:  # type: AsyncSession
        sess_row = await db.execute(
            text("SELECT group_id FROM chat_sessions WHERE id = :id"),
            {"id": session_id},
        )
        first = sess_row.mappings().first()
        if not first:
            return None
        group_id = first["group_id"]

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        start_naive = _to_utc_naive(start) if start is not None else now_utc
        end_naive = _to_utc_naive(end) if end is not None else start_naive + timedelta(seconds=1)

        tid = f"tr{uuid.uuid4().hex[:8]}"

        result = await db.execute(
            text(
                """
                INSERT INTO speech_transcripts
                    (transcript_id, session_id, group_id, user_id, speaker, text,
                     start, "end", duration, confidence, audio_url, created_at)
                VALUES
                    (:tid, :session_id, :group_id, :user_id, :speaker, :text,
                     :start, :end, :duration, :confidence, :audio_url, NOW())
                RETURNING
                    transcript_id, group_id, session_id, user_id, speaker, text,
                    start, "end", duration, confidence, created_at
                """
            ),
            {
                "tid": tid,
                "session_id": session_id,
                "group_id": group_id,
                "user_id": user_id,
                "speaker": speaker,
                "text": text.strip(),
                "start": start_naive,
                "end": end_naive,
                "duration": duration,
                "confidence": confidence,
                "audio_url": audio_url,
            },
        )
        await db.commit()
        row = result.mappings().one()
        payload = _row_to_ws_payload(row)
        # 延迟导入，避免与 ws_sessions 循环依赖
        from .ws_sessions import broadcast_transcript

        await broadcast_transcript(session_id, payload)
        return payload


def should_publish_transcript_on_audio_chunk() -> bool:
    return os.getenv("WS_PUBLISH_TRANSCRIPT_ON_AUDIO_CHUNK", "").strip() in ("1", "true", "yes")


async def publish_placeholder_transcript_for_audio_chunk(session_id: str, seq: int) -> None:
    """开发用：在收到 audio_chunk 后插入占位转写并广播。生产请关闭环境变量，由 ASR 调用 insert_speech_transcript_and_broadcast。"""
    await insert_speech_transcript_and_broadcast(
        session_id,
        text=f"（占位）已收到音频分片 #{seq}，待接入 ASR 后替换为真实转写",
        speaker="系统",
    )
