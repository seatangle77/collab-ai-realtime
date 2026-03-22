from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .ws_manager import ws_manager
from .ws_protocol import (
    build_connected,
    build_audio_chunk_ack,
    build_engagement_alert,
    build_error,
    build_pong,
    build_session_ended,
    build_transcript,
)

router = APIRouter(tags=["ws-sessions"])
MAX_AUDIO_B64_LENGTH = 1_500_000
_logger = logging.getLogger(__name__)


def _parse_envelope(raw: str) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """
    Returns (msg_type, data, error_message) where error_message follows ws envelope.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, None, build_error("INVALID_JSON", "消息必须是合法 JSON")

    if not isinstance(payload, dict):
        return None, None, build_error("INVALID_SCHEMA", "消息结构必须是对象")

    msg_type = payload.get("type")
    data = payload.get("data")
    if not isinstance(msg_type, str) or not isinstance(data, dict):
        return (
            None,
            None,
            build_error("INVALID_SCHEMA", "消息必须包含 type(string) 与 data(object)"),
        )
    return msg_type, data, None


async def broadcast_transcript(session_id: str, data: dict[str, Any]) -> None:
    await ws_manager.broadcast_to_session(session_id, build_transcript(data))


async def broadcast_engagement_alert(session_id: str, data: dict[str, Any]) -> None:
    await ws_manager.broadcast_to_session(session_id, build_engagement_alert(data))


async def broadcast_session_ended(session_id: str, data: dict[str, Any]) -> None:
    await ws_manager.broadcast_to_session(session_id, build_session_ended(data))


def _validate_audio_chunk(data: dict[str, Any]) -> tuple[bool, str | None]:
    seq = data.get("seq")
    if not isinstance(seq, int) or seq < 0:
        return False, "seq 必须是非负整数"

    mime_type = data.get("mime_type")
    if not isinstance(mime_type, str) or mime_type != "audio/webm":
        return False, "mime_type 必须为 audio/webm"

    audio_b64 = data.get("audio_b64")
    if not isinstance(audio_b64, str) or not audio_b64:
        return False, "audio_b64 不能为空"

    if len(audio_b64) > MAX_AUDIO_B64_LENGTH:
        return False, "audio_b64 过大"

    try:
        decoded = base64.b64decode(audio_b64, validate=True)
    except Exception:
        return False, "audio_b64 不是合法 base64"

    if len(decoded) == 0:
        return False, "音频分片内容为空"

    return True, None


@router.websocket("/ws/sessions/{session_id}")
async def ws_session_endpoint(websocket: WebSocket, session_id: str) -> None:
    await ws_manager.connect_session(session_id, websocket)
    try:
        await websocket.send_json(build_connected(session_id))

        while True:
            raw = await websocket.receive_text()
            msg_type, _data, parse_error = _parse_envelope(raw)
            if parse_error is not None:
                await websocket.send_json(parse_error)
                continue

            if msg_type == "ping":
                await websocket.send_json(build_pong())
                continue

            if msg_type == "audio_chunk":
                ok, err_msg = _validate_audio_chunk(_data)
                if not ok:
                    await websocket.send_json(
                        build_error("INVALID_AUDIO_CHUNK_SCHEMA", err_msg or "audio_chunk 参数非法")
                    )
                    continue
                seq = _data.get("seq")
                await websocket.send_json(build_audio_chunk_ack(seq))
                # 可选：开发环境占位转写（生产由 ASR 调用 transcript_realtime.insert_speech_transcript_and_broadcast）
                from .transcript_realtime import (
                    publish_placeholder_transcript_for_audio_chunk,
                    should_publish_transcript_on_audio_chunk,
                )

                if should_publish_transcript_on_audio_chunk():
                    try:
                        await publish_placeholder_transcript_for_audio_chunk(session_id, seq)
                    except Exception:
                        _logger.exception("占位转写写入/广播失败 session_id=%s seq=%s", session_id, seq)
                continue

            await websocket.send_json(build_error("UNKNOWN_TYPE", f"不支持的消息类型: {msg_type}"))
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.send_json(build_error("INTERNAL_ERROR", "服务内部异常"))
        except Exception:
            pass
    finally:
        await ws_manager.disconnect_session(session_id, websocket)
