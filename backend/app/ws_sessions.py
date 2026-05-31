from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
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
from .session_recordings import finalize_session_recording, save_session_audio_chunk
from .ws_manager import ws_manager
from .ws_protocol import (
    build_connected,
    build_audio_chunk_ack,
    build_engagement_alert,
    build_error,
    build_pong,
    build_session_ended,
    build_transcript_segment,
    build_transcript,
)

router = APIRouter(tags=["ws-sessions"])
MAX_AUDIO_B64_LENGTH = 1_500_000
HEARTBEAT_TIMEOUT = 150  # 秒：发起者超过此时间无 ping 则自动结束会话
CLEANUP_GRACE_SECONDS = 60  # 所有人断线后等待多少秒再兜底清理
_logger = logging.getLogger(__name__)
WS_TRACE = "[WS_TRACE]"
_cleanup_tasks: dict[str, asyncio.Task] = {}


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


async def broadcast_transcript_segment(session_id: str, data: dict[str, Any]) -> None:
    await ws_manager.broadcast_to_session(session_id, build_transcript_segment(data))


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


async def _auto_end_session(session_id: str) -> bool:
    """自动将会话标记为已结束；返回本次是否真的更新了 ongoing 会话。"""
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        result = await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET status = 'ended', ended_at = NOW(), last_updated = NOW(), active_ws_count = 0
                WHERE id = :id AND status = 'ongoing'
                """
            ),
            {"id": session_id},
        )
        await db.commit()
        ended = (result.rowcount or 0) > 0
    if not ended:
        return False
    try:
        await finalize_session_recording(session_id)
    except Exception:
        _logger.exception("finalize_session_recording 失败 session_id=%s", session_id)
    await destroy_audio_service(session_id)
    _logger.info("会话已自动结束 session_id=%s", session_id)
    return True


def _cancel_cleanup_task(session_id: str) -> None:
    task = _cleanup_tasks.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()


async def _schedule_cleanup_if_empty(session_id: str) -> None:
    _cancel_cleanup_task(session_id)
    task = asyncio.create_task(_delayed_cleanup(session_id))
    _cleanup_tasks[session_id] = task


async def _delayed_cleanup(session_id: str) -> None:
    try:
        await asyncio.sleep(CLEANUP_GRACE_SECONDS)
        _cleanup_tasks.pop(session_id, None)

        session_factory = get_sessionmaker()
        async with session_factory() as db:
            result = await db.execute(
                text("SELECT active_ws_count, status FROM chat_sessions WHERE id = :id"),
                {"id": session_id},
            )
            row = result.mappings().first()

        if not row:
            return
        if row["status"] != "ongoing":
            return
        if (row["active_ws_count"] or 0) > 0:
            return

        _logger.warning("会话无人重连超时，执行兜底清理 session_id=%s", session_id)
        ended = await _auto_end_session(session_id)
        if ended:
            await ws_manager.broadcast_to_session(
                session_id,
                build_session_ended({"session_id": session_id, "reason": "all_disconnected_timeout"}),
            )
    except asyncio.CancelledError:
        raise


async def _increment_active_ws_count(session_id: str) -> bool:
    """仅对 ongoing 会话计数 +1，返回本次是否成功计数。"""
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        result = await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET active_ws_count = active_ws_count + 1
                WHERE id = :id
                  AND status = 'ongoing'
                """
            ),
            {"id": session_id},
        )
        await db.commit()
        return (result.rowcount or 0) > 0


async def _decrement_active_ws_count(session_id: str) -> int:
    session_factory = get_sessionmaker()
    async with session_factory() as db:
        result = await db.execute(
            text(
                """
                UPDATE chat_sessions
                SET active_ws_count = GREATEST(active_ws_count - 1, 0)
                WHERE id = :id
                RETURNING active_ws_count
                """
            ),
            {"id": session_id},
        )
        await db.commit()
        row = result.mappings().first()
        return int(row["active_ws_count"] or 0) if row else 0


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
    _ALLOWED_MIME_PREFIXES = ("audio/webm", "audio/aac", "audio/mp4")
    if not isinstance(mime_type, str) or not any(mime_type.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
        return False, f"mime_type 不支持，仅接受 {', '.join(_ALLOWED_MIME_PREFIXES)}"

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
    user_id: str = ""
    token_status = "missing"
    if token:
        token_status = "present"
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub", "")
            if user_id:
                token_status = "valid"
                created_by = await _get_session_created_by(session_id)
                is_host = (created_by is not None and user_id == created_by)
            else:
                token_status = "valid_no_sub"
        except JWTError as exc:
            token_status = f"invalid:{exc.__class__.__name__}"

    counted_active_ws = False
    await ws_manager.connect_session(session_id, websocket, user_id=user_id)
    _logger.warning(
        "%s [ws_connect] session_id=%s user_id=%s token_status=%s token_len=%s is_host=%s session_conn_count=%s user_conn_count=%s online_user_ids=%s",
        WS_TRACE,
        session_id,
        user_id or "<empty>",
        token_status,
        len(token) if token else 0,
        is_host,
        ws_manager.get_session_connection_count(session_id),
        ws_manager.get_user_connection_count(session_id),
        ws_manager.get_online_user_ids(session_id),
    )
    counted_active_ws = await _increment_active_ws_count(session_id)
    if counted_active_ws:
        _cancel_cleanup_task(session_id)
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
                    ended = await _auto_end_session(session_id)
                    if ended:
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
                mime_type = _data.get("mime_type", "audio/webm")
                duration_ms = _data.get("duration_ms")
                audio_bytes = base64.b64decode(audio_b64)
                recv_started = time.perf_counter()

                _logger.info(
                    "[ws_audio] session=%s seq=%s received mime=%s audio_bytes=%d",
                    session_id,
                    seq,
                    mime_type,
                    len(audio_bytes),
                )

                try:
                    await save_session_audio_chunk(
                        session_id,
                        user_id=user_id or "unknown_user",
                        seq=seq,
                        mime_type=mime_type,
                        audio_bytes=audio_bytes,
                        duration_ms=duration_ms,
                    )
                except Exception:
                    _logger.exception("保存会话录音失败 session_id=%s seq=%s", session_id, seq)

                # 先回 ACK
                await websocket.send_json(build_audio_chunk_ack(seq))
                ack_elapsed_ms = (time.perf_counter() - recv_started) * 1000
                _logger.info(
                    "[ws_audio] session=%s seq=%s ack_sent elapsed_ms=%.1f",
                    session_id,
                    seq,
                    ack_elapsed_ms,
                )

                # 懒加载 AudioService（第一个 chunk 时创建）
                service = get_audio_service(session_id)
                if service is None:
                    try:
                        user_ids = await _get_session_member_ids(session_id)
                        session_factory = get_sessionmaker()
                        async with session_factory() as db:
                            service = await create_audio_service(session_id, db, user_ids)
                        _logger.info(
                            "[ws_audio] session=%s seq=%s audio_service_created members=%d",
                            session_id,
                            seq,
                            len(user_ids),
                        )
                    except Exception:
                        _logger.exception("AudioService 初始化失败 session_id=%s", session_id)

                # 把音频 bytes 交给 AudioService 处理
                if service is not None:
                    try:
                        handle_started = time.perf_counter()
                        await service.handle_chunk(audio_bytes, mime_type, seq=seq)
                        handle_elapsed_ms = (time.perf_counter() - handle_started) * 1000
                        if handle_elapsed_ms >= 300:
                            _logger.warning(
                                "[ws_audio] session=%s seq=%s handle_chunk_slow elapsed_ms=%.1f",
                                session_id,
                                seq,
                                handle_elapsed_ms,
                            )
                        else:
                            _logger.info(
                                "[ws_audio] session=%s seq=%s handle_chunk_done elapsed_ms=%.1f",
                                session_id,
                                seq,
                                handle_elapsed_ms,
                            )
                    except Exception:
                        _logger.exception("handle_chunk 失败 session_id=%s seq=%s", session_id, seq)
                continue

            await websocket.send_json(build_error("UNKNOWN_TYPE", f"不支持的消息类型: {msg_type}"))
    except WebSocketDisconnect:
        _logger.warning(
            "%s [ws_disconnect] session_id=%s user_id=%s reason=websocket_disconnect online_user_ids=%s",
            WS_TRACE,
            session_id,
            user_id or "<empty>",
            ws_manager.get_online_user_ids(session_id),
        )
        pass
    except Exception:
        _logger.exception(
            "%s [ws_disconnect] session_id=%s user_id=%s reason=endpoint_exception",
            WS_TRACE,
            session_id,
            user_id or "<empty>",
        )
        try:
            await websocket.send_json(build_error("INTERNAL_ERROR", "服务内部异常"))
        except Exception:
            pass
    finally:
        await ws_manager.disconnect_session(session_id, websocket)
        _logger.warning(
            "%s [ws_disconnect_final] session_id=%s user_id=%s online_user_ids=%s",
            WS_TRACE,
            session_id,
            user_id or "<empty>",
            ws_manager.get_online_user_ids(session_id),
        )
        if counted_active_ws:
            remaining_active_ws = await _decrement_active_ws_count(session_id)
            if remaining_active_ws <= 0:
                await _schedule_cleanup_if_empty(session_id)
