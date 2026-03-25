from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import text

from .audio.audio_service import (
    create_audio_service,
    destroy_audio_service,
    get_audio_service,
)
from .auth import JWT_ALGORITHM, JWT_SECRET_KEY
from .db import get_sessionmaker
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
HEARTBEAT_TIMEOUT = 30  # 秒：发起者超过此时间无 ping 则自动结束会话
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


async def _get_session_created_by(session_id: str) -> str | None:
    """查询会话的发起者 user_id（created_by 字段）"""
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        result = await db.execute(
            text("SELECT created_by FROM chat_sessions WHERE id = :id"),
            {"id": session_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return row["created_by"]


async def _auto_end_session(session_id: str) -> None:
    """心跳超时时自动将会话标记为已结束（幂等）"""
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET status = 'ended', ended_at = NOW(), last_updated = NOW()
                WHERE id = :id AND status != 'ended'
                """
            ),
            {"id": session_id},
        )
        await db.commit()
    _logger.info("会话心跳超时，已自动结束 session_id=%s", session_id)


async def _get_session_member_ids(session_id: str) -> list[str]:
    """session_id → group_id → active 成员 user_ids，用于初始化 AudioService 声纹加载"""
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        sess = await db.execute(
            text("SELECT group_id FROM chat_sessions WHERE id = :id"),
            {"id": session_id},
        )
        row = sess.mappings().first()
        if not row:
            return []
        group_id = row["group_id"]

        members = await db.execute(
            text("""
                SELECT user_id FROM group_memberships
                WHERE group_id = :gid AND status = 'active'
            """),
            {"gid": group_id},
        )
        return [r["user_id"] for r in members.mappings().all()]


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
async def ws_session_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str | None = Query(default=None),
) -> None:
    # 解析 token，判断是否为发起者
    is_host = False
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id: str = payload.get("sub", "")
            if user_id:
                created_by = await _get_session_created_by(session_id)
                is_host = (created_by is not None and user_id == created_by)
        except JWTError:
            pass  # token 无效，降级为非发起者

    await ws_manager.connect_session(session_id, websocket)
    try:
        await websocket.send_json(build_connected(session_id))

        while True:
            # 发起者：有超时检测；非发起者：正常等待
            if is_host:
                try:
                    raw = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=HEARTBEAT_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    _logger.warning("发起者心跳超时，自动结束会话 session_id=%s", session_id)
                    await _auto_end_session(session_id)
                    await ws_manager.broadcast_to_session(
                        session_id,
                        build_session_ended({"session_id": session_id, "reason": "host_timeout"}),
                    )
                    break
            else:
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
                audio_b64 = _data.get("audio_b64")
                webm_bytes = base64.b64decode(audio_b64)

                # 先回 ACK
                await websocket.send_json(build_audio_chunk_ack(seq))

                # 懒加载 AudioService（第一个 chunk 时创建）
                service = get_audio_service(session_id)
                if service is None:
                    try:
                        user_ids = await _get_session_member_ids(session_id)
                        session_factory = get_sessionmaker()
                        async with session_factory() as db:
                            service = await create_audio_service(session_id, db, user_ids)
                    except Exception:
                        _logger.exception("AudioService 初始化失败 session_id=%s", session_id)

                # 把 WebM bytes 交给 AudioService 处理
                if service is not None:
                    try:
                        await service.handle_chunk(webm_bytes)
                    except Exception:
                        _logger.exception("handle_chunk 失败 session_id=%s seq=%s", session_id, seq)
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
        await destroy_audio_service(session_id)
